import os
import cv2
import time
import threading
import base64
import numpy as np
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
from ultralytics import YOLO
import supervision as sv


app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY']         = 'workforce_monitor'
app.config['UPLOAD_FOLDER']      = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    max_http_buffer_size=10 * 1024 * 1024
)

os.makedirs('uploads', exist_ok=True)
os.makedirs('output',  exist_ok=True)


#  model & detection settings 

MODEL_PATH = 'runs/detect/workforce_monitor/staff_customer_v4/weights/best.pt'
CONF       = 0.35

# how many pixels a person needs to move before we consider them active
IDLE_MOVE_THRESHOLD = 15
# how long they need to stay still before we officially call them idle
IDLE_CONFIRM_SECS   = 3

# matching radii for confirmed tracks (pixels)
MATCH_DIST_STAFF    = 160
MATCH_DIST_CUSTOMER = 80

# matching radii for the tentative pool — intentionally a bit wider
# so minor detection jitter doesn't spawn duplicate blobs
TENT_DIST_STAFF    = 180
TENT_DIST_CUSTOMER = 100

# frames without a detection before a confirmed track goes to the graveyard
LOST_FRAMES = 60  # roughly 7 s at 8 fps

# how long we keep graveyard entries around for re-identification
GRAVEYARD_FRAMES_STAFF    = 400  # ~50 s
GRAVEYARD_FRAMES_CUSTOMER = 240  # ~30 s

# re-ID search radii — staff gets a bigger one since they move around a lot
REID_DIST_STAFF    = 300
REID_DIST_CUSTOMER = 180

# require 5 consecutive hits before promoting a tentative blob to a real track
# this cuts down on ghost IDs in busy scenes
CONFIRM_FRAMES = 5

FRAME_SKIP  = 0
INFER_SIZE  = 480


# global state 

model             = None
processing        = False
stop_flag         = threading.Event()
alert_history     = []
live_alerts       = []
total_idle_alerts = 0

# these reset at the start of each video so IDs always start from 1
_global_next_staff = 1
_global_next_cust  = 1


#  model loading 

def load_model():
    global model
    if os.path.exists(MODEL_PATH):
        print(f"[INFO] loading model from {MODEL_PATH}")
        model = YOLO(MODEL_PATH)
        print("[INFO] model ready")
        socketio.emit('model_status', {'status': 'loaded', 'path': MODEL_PATH})
    else:
        print(f"[WARN] model not found at {MODEL_PATH}")
        socketio.emit('model_status', {'status': 'not_found', 'path': MODEL_PATH})


#  small helpers 

def format_time(seconds):
    seconds = int(max(0, seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"

def get_center(x1, y1, x2, y2):
    return int((x1 + x2) / 2), int((y1 + y2) / 2)

def euclidean(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

def draw_label_box(frame, text, x1, y1, color):
    font = cv2.FONT_HERSHEY_SIMPLEX
    fs, th = 0.52, 1
    (tw, th_), _ = cv2.getTextSize(text, font, fs, th)
    cv2.rectangle(frame, (x1, y1 - th_ - 8), (x1 + tw + 6, y1), color, -1)
    cv2.putText(frame, text, (x1 + 3, y1 - 4), font, fs, (255, 255, 255), th)

def frame_to_base64(frame):
    _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return base64.b64encode(buf).decode('utf-8')


class StableTracker:

    def __init__(self):
        self.tracks      = {}   # "S3" / "C7" → track dict
        self._tent_staff = {}   # tentative pool for staff
        self._tent_cust  = {}   # tentative pool for customers
        self._grave_staff = {}  # graveyard keyed by display_id
        self._grave_cust  = {}
        self._tent_key   = 0

    def reset(self):
        self.tracks       = {}
        self._tent_staff  = {}
        self._tent_cust   = {}
        self._grave_staff = {}
        self._grave_cust  = {}
        self._tent_key    = 0

    @staticmethod
    def _alloc_id(label):
        global _global_next_staff, _global_next_cust
        if label == 'Staff':
            sid = _global_next_staff
            _global_next_staff += 1
        else:
            sid = _global_next_cust
            _global_next_cust += 1
        return sid

    @staticmethod
    def _iou(b1, b2):
        ix1 = max(b1[0], b2[0])
        iy1 = max(b1[1], b2[1])
        ix2 = min(b1[2], b2[2])
        iy2 = min(b1[3], b2[3])
        iw  = max(0, ix2 - ix1)
        ih  = max(0, iy2 - iy1)
        inter = iw * ih
        if not inter:
            return 0.0
        union = (b1[2]-b1[0])*(b1[3]-b1[1]) + (b2[2]-b2[0])*(b2[3]-b2[1]) - inter
        return inter / float(union)

    def _pred(self, t):
        return (
            t['last_pos'][0] + t.get('vx', 0),
            t['last_pos'][1] + t.get('vy', 0)
        )

    def _grave(self, label):
        return self._grave_staff if label == 'Staff' else self._grave_cust

    def _try_restore(self, label, cx, cy, x1, y1, x2, y2, video_time, frame_count):
        """
        Look for a graveyard entry close enough to (cx, cy).
        If found, restore it into self.tracks and return True.
        """
        grave  = self._grave(label)
        thresh = REID_DIST_STAFF if label == 'Staff' else REID_DIST_CUSTOMER

        best_d, best_id = thresh, None
        for did, gt in grave.items():
            d = euclidean((cx, cy), gt['last_pos'])
            if d < best_d:
                best_d, best_id = d, did

        if best_id is None:
            return False

        gt  = grave.pop(best_id)
        gap = video_time - gt['last_seen']

        if label == 'Staff':
            gt['idle_since'] += gap
        else:
            gt['first_seen'] += gap

        gt.update({
            'last_seen'  : video_time,
            'last_frame' : frame_count,
            'last_pos'   : (cx, cy),
            'bbox'       : (x1, y1, x2, y2),
            'vx': 0,
            'vy': 0,
        })

        tk = f"{label[0]}{gt['display_id']}"
        self.tracks[tk] = gt
        return True

    def update(self, det_list, video_time, frame_count,
               idle_move_threshold, idle_confirm_secs,
               live_alerts_ref, alert_history_ref):

        idle_delta    = 0
        staff_dets    = [d for d in det_list if d[6] == 'Staff']
        customer_dets = [d for d in det_list if d[6] == 'Customer']

        def _run(dets, label, tent_pool, match_dist, tent_dist, use_vel):
            nonlocal idle_delta

            confirmed = {k: v for k, v in self.tracks.items() if v['class'] == label}
            unmatched = list(dets)

            # step 1: try to match each detection to a confirmed track
            for tk, t in sorted(confirmed.items(),
                                 key=lambda kv: kv[1]['last_frame'], reverse=True):
                if not unmatched:
                    break

                pred     = self._pred(t) if use_vel else t['last_pos']
                # give extra slack when a track has been missing a few frames
                eff_dist = match_dist * (2.0 if frame_count - t['last_frame'] > 5 else 1.0)

                best_d, best_i, best_det = eff_dist, None, None
                for i, d in enumerate(unmatched):
                    dd = euclidean((d[0], d[1]), pred)
                    if dd < best_d:
                        best_d, best_i, best_det = dd, i, d

                # IoU fallback when nothing matched by distance
                if best_det is None:
                    best_iou = 0.3
                    for i, d in enumerate(unmatched):
                        iou = self._iou(t['bbox'], (d[2], d[3], d[4], d[5]))
                        if iou > best_iou:
                            best_iou, best_i, best_det = iou, i, d

                if best_det is None:
                    continue

                cx, cy, x1, y1, x2, y2, lbl = best_det
                ocx, ocy = t['last_pos']

                if use_vel:
                    a = 0.4
                    t['vx'] = a * (cx - ocx) + (1 - a) * t.get('vx', 0)
                    t['vy'] = a * (cy - ocy) + (1 - a) * t.get('vy', 0)

                moved = euclidean((cx, cy), (ocx, ocy))
                t.update({
                    'last_pos'  : (cx, cy),
                    'last_seen' : video_time,
                    'last_frame': frame_count,
                    'bbox'      : (x1, y1, x2, y2),
                })

                # staff idle/active logic
                if label == 'Staff':
                    if moved > idle_move_threshold:
                        if t['is_idle']:
                            # bank the completed idle run
                            t['idle_time'] += video_time - t['idle_since']
                            t['is_idle']    = False
                        t['idle_since'] = video_time
                    else:
                        if not t['is_idle']:
                            if video_time - t['idle_since'] >= idle_confirm_secs:
                                t['is_idle'] = True
                                now_s = datetime.now().strftime('%H:%M')
                                msg   = (f"Idle staff: Staff id:{t['display_id']} "
                                         f"idle >{idle_confirm_secs}s")
                                live_alerts_ref.insert(0, {
                                    't': 'warn', 'msg': msg,
                                    'time': now_s, 'cam': 'CAM-01'
                                })
                                alert_history_ref.insert(0, {
                                    'time': now_s, 'type': 'Idle Staff',
                                    'cam': 'CAM-01', 'desc': msg, 's': 'warn'
                                })
                                if len(live_alerts_ref) > 20:
                                    live_alerts_ref.pop()
                                idle_delta += 1

                    # compute what to display right now
                    if t['is_idle']:
                        li = t['idle_time'] + (video_time - t['idle_since'])
                    else:
                        li = t['idle_time']

                    tif               = max(0.0, video_time - t['first_seen'])
                    li                = max(0.0, min(li, tif))
                    t['_live_idle']   = li
                    t['active_time']  = tif - li
                else:
                    t['wait_time'] = max(0.0, video_time - t['first_seen'])

                unmatched.pop(best_i)

            # step 2: send remaining detections to the tentative pool
            avail = dict(tent_pool)
            still = []

            for d in unmatched:
                cx, cy, x1, y1, x2, y2, lbl = d

                best_d, best_tk = tent_dist, None
                for tk, tt in avail.items():
                    dd = euclidean((cx, cy), tt['last_pos'])
                    if dd < best_d:
                        best_d, best_tk = dd, tk

                if best_tk is not None:
                    tt = tent_pool[best_tk]
                    tt['last_pos']   = (cx, cy)
                    tt['last_frame'] = frame_count
                    tt['bbox']       = (x1, y1, x2, y2)
                    tt['hits']      += 1
                    del avail[best_tk]

                    if tt['hits'] >= CONFIRM_FRAMES:
                        # step 3a: check graveyard first
                        restored = self._try_restore(
                            lbl, cx, cy, x1, y1, x2, y2,
                            video_time, frame_count
                        )
                        if not restored:
                            # step 3b: brand new person
                            did        = self._alloc_id(lbl)
                            tk_new     = f"{lbl[0]}{did}"
                            true_first = tt['first_seen']
                            self.tracks[tk_new] = {
                                'display_id' : did,
                                'class'      : lbl,
                                'first_seen' : true_first,
                                'last_seen'  : video_time,
                                'last_frame' : frame_count,
                                'last_pos'   : (cx, cy),
                                'vx': 0,
                                'vy': 0,
                                # idle_since = now (not true_first) — avoids
                                # an instant-idle trigger on the first tick
                                'idle_since' : video_time,
                                'idle_time'  : 0.0,
                                '_live_idle' : 0.0,
                                'active_time': max(0.0, video_time - true_first),
                                'wait_time'  : max(0.0, video_time - true_first),
                                'is_idle'    : False,
                                'bbox'       : (x1, y1, x2, y2),
                            }

                        del tent_pool[best_tk]
                else:
                    still.append(d)

            # step 3b: create new tentative entries for unmatched detections
            for d in still:
                cx, cy, x1, y1, x2, y2, lbl = d
                self._tent_key += 1
                tent_pool[f"t{self._tent_key}"] = {
                    'first_seen' : video_time,
                    'last_frame' : frame_count,
                    'last_pos'   : (cx, cy),
                    'bbox'       : (x1, y1, x2, y2),
                    'hits'       : 1,
                }

        _run(staff_dets,    'Staff',    self._tent_staff,
             MATCH_DIST_STAFF,    TENT_DIST_STAFF,    use_vel=True)
        _run(customer_dets, 'Customer', self._tent_cust,
             MATCH_DIST_CUSTOMER, TENT_DIST_CUSTOMER, use_vel=False)

        # step 4: move missing confirmed tracks to the graveyard
        for k in [k for k, t in self.tracks.items()
                  if frame_count - t['last_frame'] > LOST_FRAMES]:
            t = self.tracks.pop(k)
            self._grave(t['class'])[t['display_id']] = t

        # step 5: clean up stale tentatives and graveyard entries
        for pool in (self._tent_staff, self._tent_cust):
            for k in [k for k, tt in pool.items()
                      if frame_count - tt['last_frame'] > 10]:
                del pool[k]

        for did in [did for did, gt in self._grave_staff.items()
                    if frame_count - gt['last_frame'] > GRAVEYARD_FRAMES_STAFF]:
            del self._grave_staff[did]

        for did in [did for did, gt in self._grave_cust.items()
                    if frame_count - gt['last_frame'] > GRAVEYARD_FRAMES_CUSTOMER]:
            del self._grave_cust[did]

        visible = [t for t in self.tracks.values() if t['last_frame'] == frame_count]
        return visible, idle_delta

    def summary(self):
        rows = []
        for t in self.tracks.values():
            li = t.get('_live_idle', t.get('idle_time', 0.0))
            rows.append({
                'id'         : t['display_id'],
                'class'      : t['class'],
                'active'     : format_time(t.get('active_time', 0)),
                'idle'       : format_time(li),
                'wait'       : format_time(t.get('wait_time', 0)),
                'active_secs': round(t.get('active_time', 0), 1),
                'idle_secs'  : round(li, 1),
                'wait_secs'  : round(t.get('wait_time', 0), 1),
                'is_idle'    : t.get('is_idle', False),
            })
        return rows



#  main video processing loop


def process_video(video_path, sid):
    global processing, alert_history, live_alerts, total_idle_alerts
    global _global_next_staff, _global_next_cust

    processing         = True
    stop_flag.clear()
    live_alerts        = []
    alert_history      = []
    total_idle_alerts  = 0
    _global_next_staff = 1
    _global_next_cust  = 1

    stable = StableTracker()
    # per-customer peak wait accumulators — key = customer display_id
    cust_peak_wait   = {}   # id → highest wait_secs seen
    cust_gone_frames = {}   # id → frames since last seen (for expiry)
    cap    = cv2.VideoCapture(video_path)

    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS) or 25
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"[INFO] {video_path} | {width}x{height} @ {fps:.1f}fps | {total} frames")

    tracker = sv.ByteTrack(
        track_activation_threshold=0.25,
        lost_track_buffer=int(fps * 10),
        minimum_matching_threshold=0.8,
        frame_rate=max(1, int(fps)),
    )

    socketio.emit('processing_started', {
        'video'       : os.path.basename(video_path),
        'width'       : width,
        'height'      : height,
        'fps'         : fps,
        'total_frames': total,
    }, to=sid)

    frame_count  = 0
    proc_count   = 0
    last_emit    = time.time()
    pct          = 0
    last_visible = []

    while cap.isOpened() and not stop_flag.is_set():
        ret, frame = cap.read()
        if not ret:
            break

        video_time = frame_count / fps

        if frame_count % max(1, FRAME_SKIP) == 0:
            results    = model(frame, conf=CONF, verbose=False, imgsz=INFER_SIZE)[0]
            detections = sv.Detections.from_ultralytics(results)
            if len(detections) > 0:
                detections = tracker.update_with_detections(detections)

            det_list = []
            for i in range(len(detections)):
                xyxy  = detections.xyxy[i]
                label = model.names[int(detections.class_id[i])]
                x1, y1, x2, y2 = map(int, xyxy)
                cx, cy = get_center(x1, y1, x2, y2)
                det_list.append((cx, cy, x1, y1, x2, y2, label))

            visible_tracks, idle_delta = stable.update(
                det_list, video_time, frame_count,
                IDLE_MOVE_THRESHOLD, IDLE_CONFIRM_SECS,
                live_alerts, alert_history
            )
            total_idle_alerts += idle_delta
            last_visible       = visible_tracks
            proc_count        += 1
        else:
            visible_tracks = last_visible

        # draw bounding boxes and labels
        staff_list    = []
        customer_list = []

        for t in visible_tracks:
            x1, y1, x2, y2 = t['bbox']
            did   = t['display_id']
            label = t['class']

            if label == 'Staff':
                li  = t.get('_live_idle', t.get('idle_time', 0))
                act = t.get('active_time', 0)
                col = (0, 180, 255) if t['is_idle'] else (0, 200, 0)
                staff_list.append({
                    'id'         : did,
                    'active'     : format_time(act),
                    'idle'       : format_time(li),
                    'is_idle'    : t['is_idle'],
                    'active_secs': act,
                    'idle_secs'  : li,
                })
                cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)
                draw_label_box(frame, f"Idle   : {format_time(li)}",  x1, y1 - 44, (80, 80, 80))
                draw_label_box(frame, f"Active : {format_time(act)}", x1, y1 - 24, (80, 80, 80))
                draw_label_box(frame, f"STAFF  id:{did}",             x1, y1,      col)
            else:
                wt  = t.get('wait_time', 0)
                col = (0, 140, 255)
                customer_list.append({
                    'id'      : did,
                    'wait'    : format_time(wt),
                    'wait_secs': wt,
                })
                cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)
                draw_label_box(frame, f"Wait: {format_time(wt)}", x1, y1 - 22, (80, 80, 80))
                draw_label_box(frame, f"CUSTOMER  id:{did}",      x1, y1,      col)

        sc = len(staff_list)
        cc = len(customer_list)

        # timestamp and camera label — keeping these, they're useful for recordings
        ts = datetime.now().strftime("%d-%m-%Y %a %H:%M:%S")
        cv2.putText(frame, ts, (10, height - 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.putText(frame, 'Camera 1', (width - 120, height - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        ic  = sum(1 for s in staff_list if s['is_idle'])
        ac  = sc - ic
        rat = round(ac / sc * 100) if sc else 0

        # --- accurate avg wait ---
        # Strategy: only include customers who have been tracked for at least
        # MIN_WAIT_FOR_AVG seconds. This filters out people who just walked in
        # and have a tiny wait time, which was dragging the average way down.
        # For each qualifying customer we keep their current (always-growing)
        # wait_secs — no peak needed since the tracker is monotonically counting up.
        MIN_WAIT_FOR_AVG = 30.0   # seconds a customer must be tracked before counting

        active_ids = {c['id'] for c in customer_list}

        for c in customer_list:
            cid = c['id']
            cust_peak_wait[cid] = c['wait_secs']   # always update to latest
            cust_gone_frames[cid] = 0               # reset absence counter

        # expire customers gone for more than 60s so old sessions don't persist
        for cid in list(cust_peak_wait.keys()):
            if cid not in active_ids:
                cust_gone_frames[cid] = cust_gone_frames.get(cid, 0) + 1
                if cust_gone_frames[cid] > int(fps * 60):
                    del cust_peak_wait[cid]
                    del cust_gone_frames[cid]

        # only average customers who have been waiting long enough to be meaningful
        qualified = [w for w in cust_peak_wait.values() if w >= MIN_WAIT_FOR_AVG]
        if qualified:
            avg = sum(qualified) / len(qualified)
        elif cust_peak_wait:
            # if nobody has hit the threshold yet (very start of video),
            # fall back to all tracked customers so we show something
            avg = sum(cust_peak_wait.values()) / len(cust_peak_wait)
        else:
            avg = 0.0

        now = time.time()
        if now - last_emit >= 0.1:
            last_emit = now
            pct = round(frame_count / total * 100) if total else 0
            socketio.emit('frame_data', {
                'frame'            : frame_to_base64(frame),
                'frame_num'        : frame_count,
                'progress'         : pct,
                'video_time'       : format_time(video_time),
                'staff_count'      : sc,
                'customer_count'   : cc,
                'idle_count'       : ic,
                'active_count'     : ac,
                'ratio'            : rat,
                'avg_wait'         : format_time(avg),
                'avg_wait_secs'    : round(avg, 1),
                'staff_list'       : staff_list,
                'customer_list'    : customer_list,
                'track_summary'    : stable.summary(),
                'live_alerts'      : live_alerts[:5],
                'alert_count'      : len(live_alerts),
                'total_idle_alerts': total_idle_alerts,
            }, to=sid)

        frame_count += 1

        if frame_count % 200 == 0:
            print(
                f"[INFO] {frame_count}/{total} ({pct}%)"
                f"  S:{sc}  C:{cc}"
                f"  | confirmed:{len(stable.tracks)}"
                f"  | grave S:{len(stable._grave_staff)}"
                f"  C:{len(stable._grave_cust)}"
            )

    cap.release()
    processing = False

    socketio.emit('processing_done', {
        'frames_processed' : frame_count,
        'total_frames'     : total,
        'total_idle_alerts': total_idle_alerts,
    }, to=sid)

    print(f"[INFO] done — {frame_count} frames total, {proc_count} processed")


# routes 

@app.route('/')
def index():
    return send_from_directory('templates', 'dashboard.html')


@app.route('/upload', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({'error': 'No file'}), 400
    f = request.files['video']
    if not f.filename:
        return jsonify({'error': 'No filename'}), 400
    filename = secure_filename(f.filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    f.save(path)
    return jsonify({'success': True, 'path': path, 'filename': filename})


@app.route('/status')
def status():
    return jsonify({
        'model_loaded'             : model is not None,
        'model_path'               : MODEL_PATH,
        'processing'               : processing,
        'conf'                     : CONF,
        'idle_move_threshold'      : IDLE_MOVE_THRESHOLD,
        'idle_confirm_secs'        : IDLE_CONFIRM_SECS,
        'confirm_frames'           : CONFIRM_FRAMES,
        'match_dist_staff'         : MATCH_DIST_STAFF,
        'match_dist_customer'      : MATCH_DIST_CUSTOMER,
        'tent_dist_staff'          : TENT_DIST_STAFF,
        'tent_dist_customer'       : TENT_DIST_CUSTOMER,
        'lost_frames'              : LOST_FRAMES,
        'graveyard_frames_staff'   : GRAVEYARD_FRAMES_STAFF,
        'graveyard_frames_customer': GRAVEYARD_FRAMES_CUSTOMER,
        'reid_dist_staff'          : REID_DIST_STAFF,
        'reid_dist_customer'       : REID_DIST_CUSTOMER,
        'frame_skip'               : FRAME_SKIP,
        'infer_size'               : INFER_SIZE,
    })


#  websocket handlers 

@socketio.on('connect')
def on_connect():
    print(f"[WS] client connected: {request.sid}")
    emit('connected', {'sid': request.sid})
    emit('model_status', {
        'status': 'loaded' if model else 'not_found',
        'path'  : MODEL_PATH,
    })


@socketio.on('disconnect')
def on_disconnect():
    print(f"[WS] client disconnected: {request.sid}")
    stop_flag.set()


@socketio.on('start_processing')
def on_start(data):
    global processing
    if processing:
        emit('error', {'msg': 'Already processing'})
        return
    if model is None:
        emit('error', {'msg': f'Model not loaded: {MODEL_PATH}'})
        return
    vp = data.get('path')
    if not vp or not os.path.exists(vp):
        emit('error', {'msg': f'Video not found: {vp}'})
        return
    threading.Thread(target=process_video, args=(vp, request.sid), daemon=True).start()


@socketio.on('stop_processing')
def on_stop():
    stop_flag.set()
    emit('stopped', {'msg': 'Stopped'})


@socketio.on('update_config')
def on_cfg(data):
    global CONF, IDLE_MOVE_THRESHOLD, IDLE_CONFIRM_SECS
    if 'conf'                in data: CONF                = float(data['conf'])
    if 'idle_move_threshold' in data: IDLE_MOVE_THRESHOLD = int(data['idle_move_threshold'])
    if 'idle_confirm_secs'   in data: IDLE_CONFIRM_SECS   = int(data['idle_confirm_secs'])
    emit('config_updated', {
        'conf'               : CONF,
        'idle_move_threshold': IDLE_MOVE_THRESHOLD,
        'idle_confirm_secs'  : IDLE_CONFIRM_SECS,
    })


# entry point 

if __name__ == '__main__':
    print("=" * 50)
    print("WORKFORCE MONITOR — Web Dashboard")
    print("=" * 50)
    load_model()
    print("Starting server at http://localhost:5000")
    print("=" * 50)
    port = int(os.environ.get('PORT', 5000))
    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=False,
        use_reloader=False,
        log_output=True,
        allow_unsafe_werkzeug=True,
    )
