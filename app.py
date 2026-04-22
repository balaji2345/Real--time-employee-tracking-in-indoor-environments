
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

# ── Flask setup ──────────────────────────────────────────────
app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = 'workforce_monitor_2026'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading',
                    max_http_buffer_size=10 * 1024 * 1024)

os.makedirs('uploads', exist_ok=True)
os.makedirs('output', exist_ok=True)

# ── Model / detection config ─────────────────────────────────
MODEL_PATH            = 'runs/detect/workforce_monitor/staff_customer_v4/weights/best.pt'
CONF                  = 0.35
IDLE_MOVE_THRESHOLD   = 15
IDLE_CONFIRM_SECS     = 3

# Matching radius per class (pixels)
MATCH_DIST_CUSTOMER   = 80    # tight — seated people barely move
MATCH_DIST_STAFF      = 160   # wide   — staff walk; also uses velocity prediction

# Frames before a disappeared track is pruned (~7.5 s @ 8 FPS)
LOST_FRAMES           = 60

# ── Global state ─────────────────────────────────────────────
model             = None
processing        = False
stop_flag         = threading.Event()
alert_history     = []
live_alerts       = []
total_idle_alerts = 0

# ── Load model ───────────────────────────────────────────────
def load_model():
    global model
    if os.path.exists(MODEL_PATH):
        print(f"[INFO] Loading model: {MODEL_PATH}")
        model = YOLO(MODEL_PATH)
        print("[INFO] Model loaded ✓")
        socketio.emit('model_status', {'status': 'loaded', 'path': MODEL_PATH})
    else:
        print(f"[WARN] Model not found at {MODEL_PATH}")
        socketio.emit('model_status', {'status': 'not_found', 'path': MODEL_PATH})

# ── Helpers ───────────────────────────────────────────────────
def format_time(seconds):
    seconds = int(max(0, seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"

def get_center(x1, y1, x2, y2):
    return int((x1 + x2) / 2), int((y1 + y2) / 2)

def euclidean(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

def draw_label_box(frame, text, x1, y1, color):
    font, fs, th = cv2.FONT_HERSHEY_SIMPLEX, 0.52, 1
    (tw, th_), _ = cv2.getTextSize(text, font, fs, th)
    cv2.rectangle(frame, (x1, y1 - th_ - 8), (x1 + tw + 6, y1), color, -1)
    cv2.putText(frame, text, (x1 + 3, y1 - 4), font, fs, (255, 255, 255), th)

def frame_to_base64(frame):
    _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return base64.b64encode(buf).decode('utf-8')


# ── Stable ID tracker ─────────────────────────────────────────
class StableTracker:
    

    CONFIRM_FRAMES = 3          # frames a new detection must persist before getting an ID

    def __init__(self):
        self.tracks      = {}   # key → confirmed track dict
        self._tentative  = {}   # key → tentative track dict (no display_id yet)
        self._next_staff = 1
        self._next_cust  = 1
        self._tent_key   = 0    # internal counter for tentative keys

    def reset(self):
        self.tracks      = {}
        self._tentative  = {}
        self._next_staff = 1
        self._next_cust  = 1
        self._tent_key   = 0

    def _new_id(self, label):
        if label == 'Staff':
            sid = self._next_staff;  self._next_staff += 1
        else:
            sid = self._next_cust;   self._next_cust  += 1
        return sid

    def _predicted_pos(self, t):
        """One-frame-ahead position using stored velocity (Staff only)."""
        cx, cy = t['last_pos']
        return (cx + t.get('vx', 0), cy + t.get('vy', 0))

    @staticmethod
    def _iou(b1, b2):
        """IoU between two (x1,y1,x2,y2) boxes."""
        ix1 = max(b1[0], b2[0]); iy1 = max(b1[1], b2[1])
        ix2 = min(b1[2], b2[2]); iy2 = min(b1[3], b2[3])
        iw  = max(0, ix2 - ix1); ih  = max(0, iy2 - iy1)
        inter = iw * ih
        if inter == 0:
            return 0.0
        a1 = (b1[2]-b1[0]) * (b1[3]-b1[1])
        a2 = (b2[2]-b2[0]) * (b2[3]-b2[1])
        return inter / float(a1 + a2 - inter)

    def update(self, det_list, video_time, frame_count,
               idle_move_threshold, idle_confirm_secs,
               live_alerts_ref, alert_history_ref):
        """
        det_list: [(cx, cy, x1, y1, x2, y2, label), …]

        Returns (visible_tracks, idle_alert_count)
        """
        # Separate detections by class so Staff and Customer never
        # steal each other's IDs even when standing next to each other.
        staff_dets    = [(i, d) for i, d in enumerate(det_list) if d[6] == 'Staff']
        customer_dets = [(i, d) for i, d in enumerate(det_list) if d[6] == 'Customer']

        staff_tracks    = {k: v for k, v in self.tracks.items() if v['class'] == 'Staff'}
        customer_tracks = {k: v for k, v in self.tracks.items() if v['class'] == 'Customer'}

        idle_delta = 0

        # ── Match detections to existing tracks (per class) ───────
        def match_and_update(det_subset, track_subset, match_dist, use_velocity):
            nonlocal idle_delta

            unmatched_dets = list(det_subset)   # [(orig_idx, det_tuple), …]
            matched_keys   = set()

            # Sort tracks by recency so freshest tracks get first pick
            sorted_tracks = sorted(
                track_subset.items(),
                key=lambda kv: kv[1]['last_frame'],
                reverse=True
            )

            for tk, t in sorted_tracks:
                if not unmatched_dets:
                    break

                # Predicted position (velocity extrapolation for Staff)
                pred = self._predicted_pos(t) if use_velocity else t['last_pos']

                # Use 2× radius for tracks that have been lost for a few frames
                frames_lost = frame_count - t['last_frame']
                effective_dist = match_dist * (2.0 if frames_lost > 5 else 1.0)

                # ── Pass 1: centroid distance ──────────────────
                best_d, best_i, best_det = effective_dist, None, None
                for idx, (orig_i, d) in enumerate(unmatched_dets):
                    dd = euclidean((d[0], d[1]), pred)
                    if dd < best_d:
                        best_d, best_i, best_det = dd, idx, d

                # ── Pass 2: IoU fallback if centroid failed ────
                if best_det is None:
                    best_iou = 0.3          # minimum IoU to count as a match
                    for idx, (orig_i, d) in enumerate(unmatched_dets):
                        iou = self._iou(t['bbox'], (d[2], d[3], d[4], d[5]))
                        if iou > best_iou:
                            best_iou, best_i, best_det = iou, idx, d

                if best_det is None:
                    continue

                # ── Update this track ──────────────────────────
                cx, cy, x1, y1, x2, y2, label = best_det
                old_cx, old_cy = t['last_pos']

                # Update velocity (smoothed, Staff only)
                if use_velocity:
                    alpha = 0.4   # smoothing factor: 0 = ignore new, 1 = raw
                    t['vx'] = alpha * (cx - old_cx) + (1 - alpha) * t.get('vx', 0)
                    t['vy'] = alpha * (cy - old_cy) + (1 - alpha) * t.get('vy', 0)

                moved = euclidean((cx, cy), (old_cx, old_cy))
                t['last_pos']   = (cx, cy)
                t['last_seen']  = video_time
                t['last_frame'] = frame_count
                t['bbox']       = (x1, y1, x2, y2)

                # Idle logic (Staff only)
                if label == 'Staff':
                    if moved > idle_move_threshold:
                        if t['is_idle']:
                            t['idle_time'] += video_time - t['idle_since']
                        t['is_idle']    = False
                        t['idle_since'] = video_time
                    else:
                        if not t['is_idle']:
                            if video_time - t['idle_since'] > idle_confirm_secs:
                                t['is_idle']    = True
                                t['idle_since'] = video_time
                                now = datetime.now().strftime('%H:%M')
                                msg = f"Idle staff: Staff id:{t['display_id']} idle >{idle_confirm_secs}s"
                                live_alerts_ref.insert(0, {'t': 'warn', 'msg': msg,
                                                           'time': now, 'cam': 'CAM-01'})
                                alert_history_ref.insert(0, {'time': now, 'type': 'Idle Staff',
                                                             'cam': 'CAM-01', 'desc': msg, 's': 'warn'})
                                if len(live_alerts_ref) > 20:
                                    live_alerts_ref.pop()
                                idle_delta += 1
                        else:
                            t['idle_time'] = video_time - t['idle_since']

                    t['active_time'] = max(0, video_time - t['first_seen'] - t['idle_time'])

                matched_keys.add(tk)
                unmatched_dets.pop(best_i)

            # ── Handle unmatched detections via tentative buffer ──
            # Avoids burning ID numbers on noise / partial detections.
            if det_subset:
                tent_class  = det_subset[0][1][6]   # 'Staff' or 'Customer'
            else:
                tent_class  = None

            tent_subset = {k: v for k, v in self._tentative.items()
                           if v['class'] == tent_class} if tent_class else {}

            for orig_i, d in unmatched_dets:
                cx, cy, x1, y1, x2, y2, label = d
                matched_tent = False

                # Try to match to an existing tentative track
                best_d, best_tk = match_dist, None
                for tk, tt in tent_subset.items():
                    dd = euclidean((cx, cy), tt['last_pos'])
                    if dd < best_d:
                        best_d, best_tk = dd, tk

                if best_tk is not None and best_tk in self._tentative:
                    tt = self._tentative[best_tk]
                    tt['last_pos']   = (cx, cy)
                    tt['last_frame'] = frame_count
                    tt['bbox']       = (x1, y1, x2, y2)
                    tt['hits']      += 1

                    # Graduate to confirmed track once seen enough times
                    if tt['hits'] >= self.CONFIRM_FRAMES:
                        display_id = self._new_id(label)
                        tk_new = f"{label[0]}{display_id}"
                        self.tracks[tk_new] = {
                            'display_id' : display_id,
                            'class'      : label,
                            'first_seen' : tt['first_seen'],
                            'last_seen'  : video_time,
                            'last_frame' : frame_count,
                            'last_pos'   : (cx, cy),
                            'vx'         : 0,
                            'vy'         : 0,
                            'idle_since' : video_time,
                            'idle_time'  : 0.0,
                            'active_time': 0.0,
                            'is_idle'    : False,
                            'bbox'       : (x1, y1, x2, y2),
                        }
                        del self._tentative[best_tk]
                        # Remove from snapshot so this key can't be matched again
                        tent_subset.pop(best_tk, None)
                    matched_tent = True

                if not matched_tent:
                    # Brand-new tentative track — NO display_id assigned yet
                    self._tent_key += 1
                    self._tentative[f"t{self._tent_key}"] = {
                        'class'      : label,
                        'first_seen' : video_time,
                        'last_frame' : frame_count,
                        'last_pos'   : (cx, cy),
                        'bbox'       : (x1, y1, x2, y2),
                        'hits'       : 1,
                    }

        match_and_update(staff_dets,    staff_tracks,    MATCH_DIST_STAFF,    use_velocity=True)
        match_and_update(customer_dets, customer_tracks, MATCH_DIST_CUSTOMER, use_velocity=False)

        # ── Prune stale tentative tracks (missed 10+ frames) ──────
        stale_tent = [k for k, tt in self._tentative.items()
                      if frame_count - tt['last_frame'] > 10]
        for k in stale_tent:
            del self._tentative[k]

        # ── Collect tracks visible this frame ─────────────────────
        visible = [t for t in self.tracks.values() if t['last_frame'] == frame_count]

        # ── Prune lost confirmed tracks ───────────────────────────
        lost = [k for k, t in self.tracks.items()
                if frame_count - t['last_frame'] > LOST_FRAMES]
        for k in lost:
            del self.tracks[k]

        return visible, idle_delta

    def summary(self):
        return [
            {
                'id'     : t['display_id'],
                'class'  : t['class'],
                'active' : format_time(t['active_time']),
                'idle'   : format_time(t['idle_time']),
                'is_idle': t['is_idle'],
            }
            for t in self.tracks.values()
        ]


# ── Core processing loop ──────────────────────────────────────
def process_video(video_path, sid):
    global processing, alert_history, live_alerts, total_idle_alerts

    processing        = True
    stop_flag.clear()
    live_alerts       = []
    alert_history     = []
    total_idle_alerts = 0

    stable = StableTracker()

    cap    = cv2.VideoCapture(video_path)
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS) or 25
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"[INFO] {video_path} | {width}x{height} @ {fps:.1f}fps | {total} frames")

    # ByteTrack used only for bbox smoothing — its tracker_id is ignored
    tracker = sv.ByteTrack(
        track_activation_threshold=0.25,
        lost_track_buffer=int(fps * 10),
        minimum_matching_threshold=0.8,
        frame_rate=max(1, int(fps)),
    )

    socketio.emit('processing_started', {
        'video': os.path.basename(video_path),
        'width': width, 'height': height,
        'fps': fps, 'total_frames': total
    }, to=sid)

    frame_count = 0
    last_emit   = time.time()
    pct         = 0

    while cap.isOpened() and not stop_flag.is_set():
        ret, frame = cap.read()
        if not ret:
            break

        video_time = frame_count / fps

        # ── YOLO + ByteTrack ──────────────────────────────────────
        results    = model(frame, conf=CONF, verbose=False)[0]
        detections = sv.Detections.from_ultralytics(results)
        if len(detections) > 0:
            detections = tracker.update_with_detections(detections)

        # ── Build det_list ────────────────────────────────────────
        det_list = []
        for i in range(len(detections)):
            xyxy  = detections.xyxy[i]
            label = model.names[int(detections.class_id[i])]
            x1, y1, x2, y2 = map(int, xyxy)
            cx, cy = get_center(x1, y1, x2, y2)
            det_list.append((cx, cy, x1, y1, x2, y2, label))

        # ── StableTracker update ──────────────────────────────────
        visible_tracks, idle_delta = stable.update(
            det_list, video_time, frame_count,
            IDLE_MOVE_THRESHOLD, IDLE_CONFIRM_SECS,
            live_alerts, alert_history
        )
        total_idle_alerts += idle_delta

        # ── Draw + build payload lists ────────────────────────────
        staff_list    = []
        customer_list = []

        for t in visible_tracks:
            x1, y1, x2, y2 = t['bbox']
            display_id  = t['display_id']
            label       = t['class']
            idle_secs   = t['idle_time']
            active_secs = t['active_time']
            wait_secs   = video_time - t['first_seen']

            if label == 'Staff':
                color = (0, 180, 255) if t['is_idle'] else (0, 200, 0)
                staff_list.append({
                    'id'         : display_id,
                    'active'     : format_time(active_secs),
                    'idle'       : format_time(idle_secs),
                    'is_idle'    : t['is_idle'],
                    'active_secs': active_secs,
                    'idle_secs'  : idle_secs,
                })
            else:
                color = (0, 140, 255)
                customer_list.append({
                    'id'       : display_id,
                    'wait'     : format_time(wait_secs),
                    'wait_secs': wait_secs,
                })

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            if label == 'Staff':
                draw_label_box(frame, f"Idle   : {format_time(idle_secs)}",   x1, y1 - 44, (80, 80, 80))
                draw_label_box(frame, f"Active : {format_time(active_secs)}", x1, y1 - 24, (80, 80, 80))
                draw_label_box(frame, f"STAFF  id:{display_id}",              x1, y1,      color)
            else:
                draw_label_box(frame, f"Wait: {format_time(wait_secs)}", x1, y1 - 22, (80, 80, 80))
                draw_label_box(frame, f"CUSTOMER  id:{display_id}",      x1, y1,      color)

        staff_count    = len(staff_list)
        customer_count = len(customer_list)

        # ── HUD ───────────────────────────────────────────────────
        cv2.rectangle(frame, (0, 0), (230, 70), (0, 0, 0), -1)
        cv2.putText(frame, f"Staff    : {staff_count}",    (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 0), 2)
        cv2.putText(frame, f"Customer : {customer_count}", (10, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 140, 255), 2)

        ts = datetime.now().strftime("%d-%m-%Y %a %H:%M:%S")
        cv2.putText(frame, ts,         (10, height - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.putText(frame, 'Camera 1', (width - 120, height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        # ── Analytics ─────────────────────────────────────────────
        idle_count   = sum(1 for s in staff_list if s['is_idle'])
        active_count = staff_count - idle_count
        ratio        = round(active_count / staff_count * 100) if staff_count > 0 else 0
        avg_wait     = (sum(c['wait_secs'] for c in customer_list) / len(customer_list)) if customer_list else 0

        # ── Emit every ~100ms ─────────────────────────────────────
        now = time.time()
        if now - last_emit >= 0.1:
            last_emit = now
            pct = round(frame_count / total * 100) if total > 0 else 0
            socketio.emit('frame_data', {
                'frame'      : frame_to_base64(frame),
                'frame_num'  : frame_count,
                'progress'   : pct,
                'video_time' : format_time(video_time),

                'staff_count'   : staff_count,
                'customer_count': customer_count,
                'idle_count'    : idle_count,
                'active_count'  : active_count,
                'ratio'         : ratio,
                'avg_wait'      : format_time(avg_wait),
                'avg_wait_secs' : round(avg_wait, 1),

                'staff_list'   : staff_list,
                'customer_list': customer_list,
                'track_summary': stable.summary(),

                'live_alerts'      : live_alerts[:5],
                'alert_count'      : len(live_alerts),
                'total_idle_alerts': total_idle_alerts,
            }, to=sid)

        frame_count += 1
        if frame_count % 200 == 0:
            print(f"[INFO] Frame {frame_count}/{total} ({pct}%) "
                  f"| Staff:{staff_count} Cust:{customer_count} "
                  f"| Tracks:{len(stable.tracks)}")

    cap.release()
    processing = False
    socketio.emit('processing_done', {
        'frames_processed' : frame_count,
        'total_frames'     : total,
        'total_idle_alerts': total_idle_alerts,
    }, to=sid)
    print(f"[INFO] Done: {frame_count} frames")


# ── Routes ────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('templates', 'dashboard.html')

@app.route('/upload', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({'error': 'No file'}), 400
    f = request.files['video']
    if f.filename == '':
        return jsonify({'error': 'No filename'}), 400
    filename = secure_filename(f.filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    f.save(path)
    return jsonify({'success': True, 'path': path, 'filename': filename})

@app.route('/status')
def status():
    return jsonify({
        'model_loaded'         : model is not None,
        'model_path'           : MODEL_PATH,
        'processing'           : processing,
        'conf'                 : CONF,
        'idle_move_threshold'  : IDLE_MOVE_THRESHOLD,
        'idle_confirm_secs'    : IDLE_CONFIRM_SECS,
        'match_dist_staff'     : MATCH_DIST_STAFF,
        'match_dist_customer'  : MATCH_DIST_CUSTOMER,
        'lost_frames'          : LOST_FRAMES,
    })

# ── WebSocket events ──────────────────────────────────────────
@socketio.on('connect')
def on_connect():
    print(f"[WS] Client connected: {request.sid}")
    emit('connected', {'sid': request.sid})
    emit('model_status', {'status': 'loaded' if model else 'not_found', 'path': MODEL_PATH})

@socketio.on('disconnect')
def on_disconnect():
    print(f"[WS] Client disconnected: {request.sid}")
    stop_flag.set()

@socketio.on('start_processing')
def on_start_processing(data):
    global processing
    if processing:
        emit('error', {'msg': 'Already processing a video'})
        return
    if model is None:
        emit('error', {'msg': f'Model not loaded. Check path: {MODEL_PATH}'})
        return
    video_path = data.get('path')
    if not video_path or not os.path.exists(video_path):
        emit('error', {'msg': f'Video not found: {video_path}'})
        return
    t = threading.Thread(target=process_video, args=(video_path, request.sid), daemon=True)
    t.start()

@socketio.on('stop_processing')
def on_stop():
    stop_flag.set()
    emit('stopped', {'msg': 'Processing stopped'})

@socketio.on('update_config')
def on_update_config(data):
    global CONF, IDLE_MOVE_THRESHOLD, IDLE_CONFIRM_SECS
    if 'conf' in data:                CONF                = float(data['conf'])
    if 'idle_move_threshold' in data: IDLE_MOVE_THRESHOLD = int(data['idle_move_threshold'])
    if 'idle_confirm_secs' in data:   IDLE_CONFIRM_SECS   = int(data['idle_confirm_secs'])
    print(f"[CONFIG] CONF={CONF} IDLE_MOVE={IDLE_MOVE_THRESHOLD} IDLE_SECS={IDLE_CONFIRM_SECS}")
    emit('config_updated', {
        'conf': CONF, 'idle_move_threshold': IDLE_MOVE_THRESHOLD,
        'idle_confirm_secs': IDLE_CONFIRM_SECS,
    })

# ── Start ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 50)
    print("WORKFORCE MONITOR — Web Dashboard")
    print("=" * 50)
    load_model()
    print("Starting server at http://localhost:5000")
    print("=" * 50)
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, 
             use_reloader=False, log_output=True)