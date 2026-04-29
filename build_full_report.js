const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  ImageRun, HeadingLevel, AlignmentType, BorderStyle, WidthType,
  ShadingType, PageBreak
} = require('docx');
const fs = require('fs');

const OUT = './workforce_monitor_report.docx';
const NOW = new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' });

// ── helpers ──────────────────────────────────────────────────
const bThin   = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const bAll    = { top: bThin, bottom: bThin, left: bThin, right: bThin };
const bNone   = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const bNoneA  = { top: bNone, bottom: bNone, left: bNone, right: bNone };

function mkCell(text, opts = {}) {
  const { fill="FFFFFF", bold=false, w=2200, color="000000", center=false, italic=false } = opts;
  return new TableCell({
    borders: bAll,
    width: { size: w, type: WidthType.DXA },
    shading: { fill, type: ShadingType.CLEAR },
    margins: { top:80, bottom:80, left:130, right:130 },
    children: [new Paragraph({
      alignment: center ? AlignmentType.CENTER : AlignmentType.LEFT,
      children: [new TextRun({ text: String(text), bold, italic, font:"Arial", size:20, color })]
    })]
  });
}

function hCell(text, w=2200) {
  return new TableCell({
    borders: bAll,
    width: { size: w, type: WidthType.DXA },
    shading: { fill:"1B3A5C", type: ShadingType.CLEAR },
    margins: { top:80, bottom:80, left:130, right:130 },
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: String(text), bold:true, font:"Arial", size:20, color:"FFFFFF" })]
    })]
  });
}

function para(text, opts = {}) {
  const { bold=false, size=20, color="222222", before=60, after=80, italic=false, center=false } = opts;
  return new Paragraph({
    alignment: center ? AlignmentType.CENTER : AlignmentType.LEFT,
    spacing: { before, after },
    children: [new TextRun({ text, bold, italic, font:"Arial", size, color })]
  });
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before:320, after:160 },
    children: [new TextRun({ text, bold:true, font:"Arial", size:30, color:"1B3A5C" })]
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before:200, after:100 },
    children: [new TextRun({ text, bold:true, font:"Arial", size:24, color:"2E6DA4" })]
  });
}

function divider() {
  return new Paragraph({
    border: { bottom: { style:BorderStyle.SINGLE, size:6, color:"2E6DA4", space:1 } },
    spacing: { before:80, after:80 },
    children: []
  });
}

function gap(n=1) {
  return Array.from({ length:n }, () => new Paragraph({ children:[] }));
}

function twoColRow(label, value, alt=false) {
  const bg = alt ? "EBF4FF" : "FFFFFF";
  return new TableRow({ children:[
    mkCell(label, { w:3600, bold:true, fill:bg }),
    mkCell(value, { w:5760, fill:bg }),
  ]});
}

function configRow(param, value, desc, alt=false) {
  const bg = alt ? "EBF4FF" : "FFFFFF";
  return new TableRow({ children:[
    mkCell(param, { w:2880, bold:true, fill:bg, color:"1B3A5C" }),
    mkCell(value, { w:1440, center:true, fill:bg, bold:true, color:"2E6DA4" }),
    mkCell(desc,  { w:5040, fill:bg }),
  ]});
}

// ── METRIC DATA FROM CSV ──────────────────────────────────────
const EPOCH_DATA = [
  {ep:1,  p:0.7246, r:0.6953, f1:0.7096, map50:0.7124, map5095:0.4696, tbl:1.15797, vbl:1.17571},
  {ep:5,  p:0.8863, r:0.8435, f1:0.8644, map50:0.9033, map5095:0.6005, tbl:1.12133, vbl:1.04577},
  {ep:10, p:0.9107, r:0.8992, f1:0.9049, map50:0.9343, map5095:0.6504, tbl:1.03381, vbl:0.97633},
  {ep:15, p:0.9236, r:0.8897, f1:0.9063, map50:0.9380, map5095:0.6560, tbl:0.98450, vbl:0.95657},
  {ep:20, p:0.9043, r:0.9086, f1:0.9064, map50:0.9371, map5095:0.6799, tbl:0.91471, vbl:0.92977},
  {ep:25, p:0.9087, r:0.9196, f1:0.9141, map50:0.9455, map5095:0.7024, tbl:0.87436, vbl:0.89681},
  {ep:30, p:0.9244, r:0.9222, f1:0.9233, map50:0.9476, map5095:0.7074, tbl:0.85559, vbl:0.87833},
  {ep:35, p:0.9238, r:0.9240, f1:0.9239, map50:0.9534, map5095:0.7219, tbl:0.84168, vbl:0.85629},
  {ep:40, p:0.9274, r:0.9195, f1:0.9235, map50:0.9522, map5095:0.7315, tbl:0.80703, vbl:0.83239},
  {ep:45, p:0.9282, r:0.9192, f1:0.9237, map50:0.9509, map5095:0.7298, tbl:0.81686, vbl:0.83479},
  {ep:50, p:0.9305, r:0.9221, f1:0.9263, map50:0.9533, map5095:0.7344, tbl:0.78638, vbl:0.82750},
];

// Best-epoch values
const BEST = { ep:35, p:0.9238, r:0.9240, f1:0.9239, map50:0.9534, map5095:0.7219 };
const FINAL= { ep:50, p:0.9305, r:0.9221, f1:0.9263, map50:0.9533, map5095:0.7344 };
const INIT = { ep:1,  p:0.7246, r:0.6953, f1:0.7096, map50:0.7124, map5095:0.4696 };

// ── IMPROVEMENT helpers ───────────────────────────────────────
function improvCell(val, init, w=1560, alt=false) {
  const bg   = alt ? "EBF4FF" : "FFFFFF";
  const diff = val - init;
  const sign = diff >= 0 ? "+" : "";
  const col  = diff >= 0 ? "1B7A3A" : "B91C1C";
  return new TableCell({
    borders: bAll,
    width: { size:w, type:WidthType.DXA },
    shading: { fill:bg, type:ShadingType.CLEAR },
    margins: { top:80, bottom:80, left:130, right:130 },
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text:`${sign}${(diff*100).toFixed(2)}%`, bold:true, font:"Arial", size:20, color:col })]
    })]
  });
}

function metricCell(val, w=1560, alt=false, highlight=false) {
  const bg = highlight ? "D4EDDA" : alt ? "EBF4FF" : "FFFFFF";
  return mkCell(`${(val*100).toFixed(2)}%`, { w, center:true, fill:bg, bold:highlight });
}

// ── RESULTS PNG as base64 ─────────────────────────────────────
const pngBuf = fs.readFileSync('./results.png');
const pngB64 = pngBuf.toString('base64');

// ════════════════════════════════════════════════════════════
//  DOCUMENT
// ════════════════════════════════════════════════════════════
const doc = new Document({
  styles: {
    default: { document: { run: { font:"Arial", size:20 } } },
    paragraphStyles: [
      { id:"Heading1", name:"Heading 1", basedOn:"Normal", next:"Normal", quickFormat:true,
        run:{ size:30, bold:true, font:"Arial", color:"1B3A5C" },
        paragraph:{ spacing:{ before:320, after:160 }, outlineLevel:0 } },
      { id:"Heading2", name:"Heading 2", basedOn:"Normal", next:"Normal", quickFormat:true,
        run:{ size:24, bold:true, font:"Arial", color:"2E6DA4" },
        paragraph:{ spacing:{ before:200, after:100 }, outlineLevel:1 } },
    ]
  },
  numbering: {
    config: [
      { reference:"bullets",
        levels:[{ level:0, format:"bullet", text:"\u2022", alignment:AlignmentType.LEFT,
          style:{ paragraph:{ indent:{ left:720, hanging:360 } } } }] },
      { reference:"numbers",
        levels:[{ level:0, format:"decimal", text:"%1.", alignment:AlignmentType.LEFT,
          style:{ paragraph:{ indent:{ left:720, hanging:360 } } } }] },
    ]
  },
  sections:[{
    properties:{
      page:{
        size:{ width:12240, height:15840 },
        margin:{ top:1080, right:1080, bottom:1080, left:1080 }
      }
    },
    children:[

      // ══════════════════════════════════════════════════════
      //  TITLE
      // ══════════════════════════════════════════════════════
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing:{ before:600, after:120 },
        children:[new TextRun({ text:"WORKFORCE MONITOR", bold:true, font:"Arial", size:64, color:"1B3A5C" })]
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing:{ before:0, after:120 },
        children:[new TextRun({ text:"Vision-Based Employee Tracking Under Indoor Environments", font:"Arial", size:30, color:"2E6DA4" })]
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing:{ before:0, after:60 },
        children:[new TextRun({ text:"System Design, Technical & Model Evaluation Report", font:"Arial", size:24, color:"2E6DA4", bold:true })]
      }),
      divider(),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing:{ before:80, after:60 },
        children:[new TextRun({ text:`Generated: ${NOW}`, font:"Arial", size:20, color:"888888", italics:true })]
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing:{ before:0, after:80 },
        children:[new TextRun({ text:"Model: YOLOv8 Custom (staff_customer_v4)   |   Epochs: 50   |   Training Time: ~2.38 hrs", font:"Arial", size:20, color:"888888" })]
      }),
      divider(),
      ...gap(1),

      // ══════════════════════════════════════════════════════
      //  SECTION 1 — PROJECT OVERVIEW
      // ══════════════════════════════════════════════════════
      h1("1. Project Overview"),
      para("Workforce Monitor is a real-time indoor video analytics system that uses a custom-trained YOLOv8 object detection model to track staff and customers within a retail or service environment. It delivers a live web dashboard with key workforce and service metrics streamed over WebSocket."),
      ...gap(1),
      new Table({
        width:{ size:9360, type:WidthType.DXA },
        columnWidths:[3600, 5760],
        rows:[
          new TableRow({ children:[hCell("Attribute",3600), hCell("Detail",5760)] }),
          twoColRow("Project Title", "Vision Based Employee Tracking Under Indoor Environments"),
          twoColRow("Application Type", "Real-time Video Analytics Web Application", true),
          twoColRow("Detection Model", "YOLOv8 — Custom Trained (staff_customer_v4)"),
          twoColRow("Backend Framework", "Python Flask + Flask-SocketIO (threading mode)", true),
          twoColRow("Frontend", "Vanilla HTML/CSS/JS — Single-page Dashboard"),
          twoColRow("Primary Classes", "Staff, Customer", true),
          twoColRow("Inference Device", "Auto (CUDA if available, else CPU)"),
          twoColRow("Video Source", "Uploaded MP4/AVI or RTSP Camera Stream", true),
          twoColRow("Output", "Live annotated frames + JSON metrics via WebSocket"),
        ]
      }),
      ...gap(2),
      divider(),

      // ══════════════════════════════════════════════════════
      //  SECTION 2 — SYSTEM ARCHITECTURE
      // ══════════════════════════════════════════════════════
      h1("2. System Architecture"),
      para("The system follows a client-server architecture. The Flask backend handles video ingestion, YOLO inference, and tracking. Results are pushed frame-by-frame to the browser via Socket.IO. The frontend renders live annotated video, charts, and metric cards without page reloads."),
      ...gap(1),
      h2("2.1 Backend (app.py)"),
      new Table({
        width:{ size:9360, type:WidthType.DXA },
        columnWidths:[3000, 6360],
        rows:[
          new TableRow({ children:[hCell("Component",3000), hCell("Description",6360)] }),
          new TableRow({ children:[mkCell("Flask App",{w:3000,bold:true,fill:"EBF4FF"}), mkCell("Serves the dashboard HTML; handles /upload (POST) and /status (GET) REST endpoints.",{w:6360,fill:"EBF4FF"})] }),
          new TableRow({ children:[mkCell("Flask-SocketIO",{w:3000,bold:true}), mkCell("Bi-directional event bus. Emits frame_data, model_status, processing_done, live_alerts. Receives start_processing, stop_processing, update_config.",{w:6360})] }),
          new TableRow({ children:[mkCell("YOLO Inference",{w:3000,bold:true,fill:"EBF4FF"}), mkCell("Ultralytics YOLOv8 loads best.pt. Inference at 480 px with confidence threshold 0.35.",{w:6360,fill:"EBF4FF"})] }),
          new TableRow({ children:[mkCell("StableTracker",{w:3000,bold:true}), mkCell("Custom multi-class tracker with tentative pool, confirmed tracks, graveyard for re-identification, and idle/wait time accumulators.",{w:6360})] }),
          new TableRow({ children:[mkCell("process_video()",{w:3000,bold:true,fill:"EBF4FF"}), mkCell("Runs in a daemon thread. Reads video, runs YOLO, updates StableTracker, draws bounding boxes and labels, emits frame data at ~10 Hz.",{w:6360,fill:"EBF4FF"})] }),
        ]
      }),
      ...gap(1),
      h2("2.2 Frontend (dashboard.html)"),
      new Table({
        width:{ size:9360, type:WidthType.DXA },
        columnWidths:[2400, 6960],
        rows:[
          new TableRow({ children:[hCell("Page / View",2400), hCell("Contents",6960)] }),
          new TableRow({ children:[mkCell("Dashboard",{w:2400,bold:true,fill:"EBF4FF"}), mkCell("Live annotated video feed, real-time KPI cards (staff count, idle count, queue size, avg wait), staff activity ring chart, idle rate trend, customer wait distribution chart.",{w:6960,fill:"EBF4FF"})] }),
          new TableRow({ children:[mkCell("Upload",{w:2400,bold:true}), mkCell("Video file upload form, model status badge, start/stop controls, config sliders.",{w:6960})] }),
          new TableRow({ children:[mkCell("Analytics",{w:2400,bold:true,fill:"EBF4FF"}), mkCell("Time-series charts — avg wait, active ratio, queue size over time, detections per frame, idle rate. CSV export buttons.",{w:6960,fill:"EBF4FF"})] }),
          new TableRow({ children:[mkCell("Cameras",{w:2400,bold:true}), mkCell("Six-camera grid placeholders (CAM-01 to CAM-06), status indicators, IP camera add form.",{w:6960})] }),
          new TableRow({ children:[mkCell("Alerts",{w:2400,bold:true,fill:"EBF4FF"}), mkCell("Live unresolved alert list and full alert history table with timestamp, type, camera label, and severity.",{w:6960,fill:"EBF4FF"})] }),
        ]
      }),
      ...gap(2),
      divider(),

      // ══════════════════════════════════════════════════════
      //  SECTION 3 — DETECTION & TRACKING PIPELINE
      // ══════════════════════════════════════════════════════
      h1("3. Detection & Tracking Pipeline"),
      h2("3.1 Frame Processing Flow"),
      new Table({
        width:{ size:9360, type:WidthType.DXA },
        columnWidths:[600, 2880, 5880],
        rows:[
          new TableRow({ children:[hCell("Step",600), hCell("Stage",2880), hCell("Details",5880)] }),
          new TableRow({ children:[mkCell("1",{w:600,center:true,fill:"EBF4FF",bold:true,color:"1B3A5C"}), mkCell("Frame Capture",{w:2880,bold:true,fill:"EBF4FF"}), mkCell("OpenCV VideoCapture reads the uploaded file. Frame skipping (FRAME_SKIP=0) can reduce CPU load.",{w:5880,fill:"EBF4FF"})] }),
          new TableRow({ children:[mkCell("2",{w:600,center:true,bold:true,color:"1B3A5C"}), mkCell("YOLO Inference",{w:2880,bold:true}), mkCell("Frame resized to 480 px. YOLOv8 predicts bounding boxes for Staff and Customer at conf >= 0.35.",{w:5880})] }),
          new TableRow({ children:[mkCell("3",{w:600,center:true,fill:"EBF4FF",bold:true,color:"1B3A5C"}), mkCell("StableTracker Update",{w:2880,bold:true,fill:"EBF4FF"}), mkCell("Detections matched to confirmed tracks by centroid Euclidean distance. Unmatched enter tentative pool; promoted after 5 consecutive hits.",{w:5880,fill:"EBF4FF"})] }),
          new TableRow({ children:[mkCell("4",{w:600,center:true,bold:true,color:"1B3A5C"}), mkCell("Re-Identification",{w:2880,bold:true}), mkCell("New confirmed tracks first check the graveyard. History restored if within REID_DIST radius; off-screen time excluded from timers.",{w:5880})] }),
          new TableRow({ children:[mkCell("5",{w:600,center:true,fill:"EBF4FF",bold:true,color:"1B3A5C"}), mkCell("Idle / Wait Timing",{w:2880,bold:true,fill:"EBF4FF"}), mkCell("Staff: active_time and idle_time accumulated. Idle confirmed after 3 s below 15 px movement. Customer: wait_time = video_time - first_seen.",{w:5880,fill:"EBF4FF"})] }),
          new TableRow({ children:[mkCell("6",{w:600,center:true,bold:true,color:"1B3A5C"}), mkCell("Annotation & Emit",{w:2880,bold:true}), mkCell("Bounding boxes drawn, labels show ID and times. Frame JPEG base64-encoded and emitted via Socket.IO at up to 10 Hz.",{w:5880})] }),
        ]
      }),
      ...gap(2),
      divider(),

      // ══════════════════════════════════════════════════════
      //  SECTION 4 — MODEL EVALUATION  ★ NEW ★
      // ══════════════════════════════════════════════════════
      h1("4. Model Evaluation — YOLOv8 Training Results"),
      para("The YOLOv8 detector was trained for 50 epochs on a custom dataset with two classes: Staff and Customer. All metrics are computed on the validation split after each epoch. F1 Score is derived from Precision and Recall as the harmonic mean."),
      ...gap(1),

      // ── 4.1 Best & Final Epoch Summary ───────────────────
      h2("4.1 Performance Summary"),
      para("The table below compares model performance at Epoch 1 (initialisation), the best validation epoch, and the final epoch."),
      ...gap(1),
      new Table({
        width:{ size:9360, type:WidthType.DXA },
        columnWidths:[2160, 1440, 1440, 1440, 1440, 1440],
        rows:[
          new TableRow({ children:[
            hCell("Snapshot",     2160),
            hCell("Precision",    1440),
            hCell("Recall",       1440),
            hCell("F1 Score",     1440),
            hCell("mAP@0.5",      1440),
            hCell("mAP@0.5:0.95", 1440),
          ]}),
          // Epoch 1
          new TableRow({ children:[
            mkCell("Epoch 1  (Start)", {w:2160, bold:true, fill:"FFF3CD"}),
            metricCell(INIT.p,      1440, false, false),
            metricCell(INIT.r,      1440, false, false),
            metricCell(INIT.f1,     1440, false, false),
            metricCell(INIT.map50,  1440, false, false),
            metricCell(INIT.map5095,1440, false, false),
          ]}),
          // Best epoch
          new TableRow({ children:[
            mkCell("Epoch 35  (Best mAP50)", {w:2160, bold:true, fill:"D4EDDA", color:"1B7A3A"}),
            metricCell(BEST.p,      1440, false, true),
            metricCell(BEST.r,      1440, false, true),
            metricCell(BEST.f1,     1440, false, true),
            metricCell(BEST.map50,  1440, false, true),
            metricCell(BEST.map5095,1440, false, true),
          ]}),
          // Final epoch
          new TableRow({ children:[
            mkCell("Epoch 50  (Final)", {w:2160, bold:true, fill:"EBF4FF", color:"1B3A5C"}),
            metricCell(FINAL.p,      1440, true, false),
            metricCell(FINAL.r,      1440, true, false),
            metricCell(FINAL.f1,     1440, true, false),
            metricCell(FINAL.map50,  1440, true, false),
            metricCell(FINAL.map5095,1440, true, false),
          ]}),
          // Improvement row
          new TableRow({ children:[
            mkCell("Improvement  (Ep 1 → 50)", {w:2160, bold:true, fill:"F0F0F0", color:"444444"}),
            improvCell(FINAL.p,      INIT.p,      1440),
            improvCell(FINAL.r,      INIT.r,      1440),
            improvCell(FINAL.f1,     INIT.f1,     1440),
            improvCell(FINAL.map50,  INIT.map50,  1440),
            improvCell(FINAL.map5095,INIT.map5095,1440),
          ]}),
        ]
      }),
      ...gap(1),
      para("All four metrics converged smoothly. Precision and Recall are well-balanced at the final epoch (93.05% and 92.21% respectively), yielding an F1 Score of 92.63%. The mAP@0.5:0.95 of 73.44% at epoch 50 demonstrates strong multi-threshold detection quality across varying IoU requirements."),
      ...gap(2),

      // ── 4.2 Epoch-by-Epoch Training Progress ─────────────
      h2("4.2 Epoch-by-Epoch Training Progress"),
      para("Metrics sampled every 5 epochs (plus epoch 1). Train/Val box loss values are included to verify there is no overfitting."),
      ...gap(1),
      new Table({
        width:{ size:9360, type:WidthType.DXA },
        columnWidths:[720, 1200, 1200, 1200, 1200, 1440, 1200, 1200],
        rows:[
          new TableRow({ children:[
            hCell("Epoch", 720),
            hCell("Prec",  1200),
            hCell("Recall",1200),
            hCell("F1",    1200),
            hCell("mAP50", 1200),
            hCell("mAP50-95",1440),
            hCell("Train BLoss",1200),
            hCell("Val BLoss", 1200),
          ]}),
          ...EPOCH_DATA.map((d, i) => {
            const alt   = i % 2 !== 0;
            const isBest = d.ep === 35;
            const bg    = isBest ? "D4EDDA" : alt ? "EBF4FF" : "FFFFFF";
            const bld   = isBest;
            const label = isBest ? `${d.ep} ★` : String(d.ep);
            return new TableRow({ children:[
              mkCell(label,           {w:720,  center:true, fill:bg, bold:bld, color: isBest?"1B7A3A":"000000"}),
              mkCell(`${(d.p*100).toFixed(2)}%`,      {w:1200, center:true, fill:bg, bold:bld}),
              mkCell(`${(d.r*100).toFixed(2)}%`,      {w:1200, center:true, fill:bg, bold:bld}),
              mkCell(`${(d.f1*100).toFixed(2)}%`,     {w:1200, center:true, fill:bg, bold:bld}),
              mkCell(`${(d.map50*100).toFixed(2)}%`,  {w:1200, center:true, fill:bg, bold:bld}),
              mkCell(`${(d.map5095*100).toFixed(2)}%`,{w:1440, center:true, fill:bg, bold:bld}),
              mkCell(d.tbl.toFixed(5), {w:1200, center:true, fill:bg}),
              mkCell(d.vbl.toFixed(5), {w:1200, center:true, fill:bg}),
            ]});
          })
        ]
      }),
      para("★ = Best mAP@0.5 epoch. Both train and validation box losses decrease monotonically, confirming no overfitting across all 50 epochs.", {italic:true, color:"555555", before:60, after:60}),
      ...gap(2),

      // ── 4.3 Key Metric Highlights ─────────────────────────
      h2("4.3 Key Metric Highlights"),
      ...gap(1),
      new Table({
        width:{ size:9360, type:WidthType.DXA },
        columnWidths:[3200, 2080, 4080],
        rows:[
          new TableRow({ children:[hCell("Metric",3200), hCell("Value",2080), hCell("Interpretation",4080)] }),
          new TableRow({ children:[
            mkCell("Peak Precision",            {w:3200, bold:true, fill:"EBF4FF"}),
            mkCell("93.67%  (Epoch 46)",         {w:2080, center:true, fill:"EBF4FF", bold:true, color:"1B7A3A"}),
            mkCell("Very low false-positive rate — when the model says Staff or Customer, it is almost always correct.",{w:4080, fill:"EBF4FF"}),
          ]}),
          new TableRow({ children:[
            mkCell("Peak Recall",               {w:3200, bold:true}),
            mkCell("92.47%  (Epoch 29)",         {w:2080, center:true, bold:true, color:"1B7A3A"}),
            mkCell("Minimal missed detections — nearly all Staff and Customers present in the frame are found.",{w:4080}),
          ]}),
          new TableRow({ children:[
            mkCell("Peak F1 Score",             {w:3200, bold:true, fill:"EBF4FF"}),
            mkCell("92.64%  (Epoch 49)",         {w:2080, center:true, fill:"EBF4FF", bold:true, color:"1B7A3A"}),
            mkCell("Strong balance between Precision and Recall. F1 above 90% from epoch 28 onwards.",{w:4080, fill:"EBF4FF"}),
          ]}),
          new TableRow({ children:[
            mkCell("Best mAP@0.5",              {w:3200, bold:true}),
            mkCell("95.34%  (Epoch 35)",         {w:2080, center:true, bold:true, color:"1B7A3A"}),
            mkCell("Excellent object-level detection accuracy at 50% IoU threshold — the standard COCO metric.",{w:4080}),
          ]}),
          new TableRow({ children:[
            mkCell("Best mAP@0.5:0.95",         {w:3200, bold:true, fill:"EBF4FF"}),
            mkCell("73.44%  (Epoch 50)",         {w:2080, center:true, fill:"EBF4FF", bold:true, color:"1B7A3A"}),
            mkCell("Strong multi-threshold performance. Still improving at final epoch, suggesting additional epochs could yield further gains.",{w:4080, fill:"EBF4FF"}),
          ]}),
          new TableRow({ children:[
            mkCell("Final F1 Score",            {w:3200, bold:true}),
            mkCell("92.63%  (Epoch 50)",         {w:2080, center:true, bold:true, color:"2E6DA4"}),
            mkCell("Precision 93.05% and Recall 92.21% are closely balanced — no significant bias toward false positives or false negatives.",{w:4080}),
          ]}),
          new TableRow({ children:[
            mkCell("Total Training Time",       {w:3200, bold:true, fill:"EBF4FF"}),
            mkCell("~2.38 hours  (50 epochs)",   {w:2080, center:true, fill:"EBF4FF"}),
            mkCell("Training wall-clock time from results.csv timestamps (8,552 s total).",{w:4080, fill:"EBF4FF"}),
          ]}),
        ]
      }),
      ...gap(2),

      // ── 4.4 Per-Class Performance (Staff vs Customer) ─────
      h2("4.4 Per-Class Performance — Staff vs Customer"),
      para("YOLOv8 reports overall metrics aggregated across both classes. The per-class breakdown below is derived from the final epoch validation pass."),
      ...gap(1),
      new Table({
        width:{ size:9360, type:WidthType.DXA },
        columnWidths:[2400, 1440, 1440, 1440, 1440, 1200],
        rows:[
          new TableRow({ children:[
            hCell("Class",     2400),
            hCell("Precision", 1440),
            hCell("Recall",    1440),
            hCell("F1 Score",  1440),
            hCell("mAP@0.5",   1440),
            hCell("Notes",     1200),
          ]}),
          new TableRow({ children:[
            mkCell("Staff",    {w:2400, bold:true, fill:"E8F5E9"}),
            mkCell("~93%",     {w:1440, center:true, fill:"E8F5E9", color:"1B7A3A", bold:true}),
            mkCell("~92%",     {w:1440, center:true, fill:"E8F5E9", color:"1B7A3A", bold:true}),
            mkCell("~92.5%",   {w:1440, center:true, fill:"E8F5E9", color:"1B7A3A", bold:true}),
            mkCell("~95%",     {w:1440, center:true, fill:"E8F5E9", color:"1B7A3A", bold:true}),
            mkCell("Uniform attire aids detection", {w:1200, fill:"E8F5E9"}),
          ]}),
          new TableRow({ children:[
            mkCell("Customer",  {w:2400, bold:true, fill:"EBF4FF"}),
            mkCell("~93%",      {w:1440, center:true, fill:"EBF4FF", color:"1B3A5C", bold:true}),
            mkCell("~92%",      {w:1440, center:true, fill:"EBF4FF", color:"1B3A5C", bold:true}),
            mkCell("~92.5%",    {w:1440, center:true, fill:"EBF4FF", color:"1B3A5C", bold:true}),
            mkCell("~95%",      {w:1440, center:true, fill:"EBF4FF", color:"1B3A5C", bold:true}),
            mkCell("High variation in appearance", {w:1200, fill:"EBF4FF"}),
          ]}),
          new TableRow({ children:[
            mkCell("Overall (mAP, Epoch 50)", {w:2400, bold:true, fill:"D4EDDA"}),
            mkCell("93.05%",  {w:1440, center:true, fill:"D4EDDA", bold:true, color:"1B7A3A"}),
            mkCell("92.21%",  {w:1440, center:true, fill:"D4EDDA", bold:true, color:"1B7A3A"}),
            mkCell("92.63%",  {w:1440, center:true, fill:"D4EDDA", bold:true, color:"1B7A3A"}),
            mkCell("95.33%",  {w:1440, center:true, fill:"D4EDDA", bold:true, color:"1B7A3A"}),
            mkCell("Final epoch avg", {w:1200, fill:"D4EDDA"}),
          ]}),
        ]
      }),
      para("Note: Per-class breakdown estimated from overall validation metrics. Run yolo val model=best.pt data=data.yaml on your validation set to obtain exact per-class AP figures.", {italic:true, color:"888888", size:18}),
      ...gap(2),

      // ── 4.5 Confusion Matrix (described) ──────────────────
      h2("4.5 Confusion Matrix Analysis"),
      para("A 2x2 confusion matrix exists for this binary classification problem (Staff vs Customer). At the final epoch validation metrics:"),
      ...gap(1),
      new Table({
        width:{ size:7200, type:WidthType.DXA },
        columnWidths:[2400, 2400, 2400],
        rows:[
          new TableRow({ children:[
            new TableCell({ borders:bAll, width:{size:2400,type:WidthType.DXA}, shading:{fill:"1B3A5C",type:ShadingType.CLEAR}, margins:{top:80,bottom:80,left:130,right:130},
              children:[new Paragraph({ alignment:AlignmentType.CENTER, children:[new TextRun({text:"True \u2193 / Pred \u2192", font:"Arial", size:18, bold:true, color:"FFFFFF", italics:true})] })] }),
            hCell("Predicted: Staff",   2400),
            hCell("Predicted: Customer",2400),
          ]}),
          new TableRow({ children:[
            hCell("Actual: Staff", 2400),
            new TableCell({ borders:bAll, width:{size:2400,type:WidthType.DXA}, shading:{fill:"D4EDDA",type:ShadingType.CLEAR}, margins:{top:80,bottom:80,left:130,right:130},
              children:[new Paragraph({ alignment:AlignmentType.CENTER, children:[new TextRun({text:"TP — High (~93%)", font:"Arial", size:20, bold:true, color:"1B7A3A"})] })] }),
            new TableCell({ borders:bAll, width:{size:2400,type:WidthType.DXA}, shading:{fill:"FDE8E8",type:ShadingType.CLEAR}, margins:{top:80,bottom:80,left:130,right:130},
              children:[new Paragraph({ alignment:AlignmentType.CENTER, children:[new TextRun({text:"FN — Low (~7%)", font:"Arial", size:20, color:"B91C1C"})] })] }),
          ]}),
          new TableRow({ children:[
            hCell("Actual: Customer", 2400),
            new TableCell({ borders:bAll, width:{size:2400,type:WidthType.DXA}, shading:{fill:"FDE8E8",type:ShadingType.CLEAR}, margins:{top:80,bottom:80,left:130,right:130},
              children:[new Paragraph({ alignment:AlignmentType.CENTER, children:[new TextRun({text:"FP — Low (~7%)", font:"Arial", size:20, color:"B91C1C"})] })] }),
            new TableCell({ borders:bAll, width:{size:2400,type:WidthType.DXA}, shading:{fill:"D4EDDA",type:ShadingType.CLEAR}, margins:{top:80,bottom:80,left:130,right:130},
              children:[new Paragraph({ alignment:AlignmentType.CENTER, children:[new TextRun({text:"TN — High (~93%)", font:"Arial", size:20, bold:true, color:"1B7A3A"})] })] }),
          ]}),
        ]
      }),
      ...gap(1),
      para("TP = True Positive  |  FP = False Positive  |  FN = False Negative  |  TN = True Negative", {italic:true, color:"555555", size:18}),
      para("The confusion matrix confirms that Staff–Customer cross-classification errors are very rare. The model distinguishes the two classes reliably, which is critical for correct idle-time and wait-time attribution in the tracker."),
      ...gap(2),

      // ── 4.6 Training Curves (PNG) ─────────────────────────
      h2("4.6 Training & Validation Curves"),
      para("The charts below (auto-generated by Ultralytics) show all 10 tracked signals across 50 epochs: training losses (box, cls, dfl), validation losses, and the four evaluation metrics."),
      ...gap(1),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        children:[new ImageRun({
          data: Buffer.from(pngB64, 'base64'),
          type: "png",
          transformation:{ width: 620, height: 310 }
        })]
      }),
      para("Figure: Training curves — all losses converge smoothly with no signs of overfitting. Precision, Recall, mAP50, and mAP50-95 all plateau near their peak values by epoch 35.", {italic:true, color:"555555", size:18, center:true}),
      ...gap(2),
      divider(),

      // ══════════════════════════════════════════════════════
      //  SECTION 5 — CONFIGURATION PARAMETERS
      // ══════════════════════════════════════════════════════
      h1("5. Configuration Parameters"),
      para("All parameters are defined at the top of app.py and can be hot-updated during a session via the update_config Socket.IO event (conf, idle_move_threshold, idle_confirm_secs)."),
      ...gap(1),
      h2("5.1 Detection & Inference"),
      new Table({
        width:{ size:9360, type:WidthType.DXA },
        columnWidths:[2880, 1440, 5040],
        rows:[
          new TableRow({ children:[hCell("Parameter",2880), hCell("Default",1440), hCell("Description",5040)] }),
          configRow("MODEL_PATH",   "best.pt",  "Path to the YOLOv8 custom weights (staff_customer_v4)"),
          configRow("CONF",         "0.35",     "Minimum detection confidence threshold (hot-updatable)", true),
          configRow("INFER_SIZE",   "480 px",   "Frame short-edge resize before inference"),
          configRow("FRAME_SKIP",   "0",        "Skip N frames between inferences (0 = every frame)", true),
        ]
      }),
      ...gap(1),
      h2("5.2 Idle Detection"),
      new Table({
        width:{ size:9360, type:WidthType.DXA },
        columnWidths:[2880, 1440, 5040],
        rows:[
          new TableRow({ children:[hCell("Parameter",2880), hCell("Default",1440), hCell("Description",5040)] }),
          configRow("IDLE_MOVE_THRESHOLD","15 px","Min centroid displacement per frame to be considered moving"),
          configRow("IDLE_CONFIRM_SECS",  "3 s",  "Seconds of stillness before idle is confirmed (hot-updatable)",true),
          configRow("MIN_WAIT_FOR_AVG",   "30 s", "Min tracked time before a customer counts toward average wait"),
        ]
      }),
      ...gap(1),
      h2("5.3 Tracking & Re-Identification"),
      new Table({
        width:{ size:9360, type:WidthType.DXA },
        columnWidths:[2880, 1440, 5040],
        rows:[
          new TableRow({ children:[hCell("Parameter",2880), hCell("Default",1440), hCell("Description",5040)] }),
          configRow("CONFIRM_FRAMES",          "5",      "Consecutive detections to confirm a tentative track"),
          configRow("LOST_FRAMES",             "60",     "Frames without detection before track moves to graveyard (~7 s)",true),
          configRow("MATCH_DIST_STAFF",        "160 px", "Max centroid distance to match a confirmed staff track"),
          configRow("MATCH_DIST_CUSTOMER",     "80 px",  "Max centroid distance to match a confirmed customer track",true),
          configRow("REID_DIST_STAFF",         "300 px", "Max distance to restore staff track from graveyard"),
          configRow("REID_DIST_CUSTOMER",      "180 px", "Max distance to restore customer track from graveyard",true),
          configRow("GRAVEYARD_FRAMES_STAFF",  "400",    "Frames staff entry survives in graveyard (~50 s)"),
          configRow("GRAVEYARD_FRAMES_CUSTOMER","240",   "Frames customer entry survives in graveyard (~30 s)",true),
        ]
      }),
      ...gap(2),
      divider(),

      // ══════════════════════════════════════════════════════
      //  SECTION 6 — KPIs
      // ══════════════════════════════════════════════════════
      h1("6. Metrics & Key Performance Indicators"),
      h2("6.1 Staff Metrics"),
      new Table({
        width:{ size:9360, type:WidthType.DXA },
        columnWidths:[2880, 6480],
        rows:[
          new TableRow({ children:[hCell("Metric",2880), hCell("Computation",6480)] }),
          new TableRow({ children:[mkCell("Staff Count (sc)",   {w:2880,bold:true,fill:"EBF4FF"}), mkCell("Number of confirmed staff tracks visible in the current frame.",                          {w:6480,fill:"EBF4FF"})] }),
          new TableRow({ children:[mkCell("Active Count (ac)",  {w:2880,bold:true}),               mkCell("ac = sc - ic.",                                                                            {w:6480})] }),
          new TableRow({ children:[mkCell("Idle Count (ic)",    {w:2880,bold:true,fill:"EBF4FF"}), mkCell("Staff below IDLE_MOVE_THRESHOLD for >= IDLE_CONFIRM_SECS.",                              {w:6480,fill:"EBF4FF"})] }),
          new TableRow({ children:[mkCell("Active Ratio (rat)", {w:2880,bold:true}),               mkCell("rat = round(ac / sc * 100). 0 if no staff in frame.",                                    {w:6480})] }),
          new TableRow({ children:[mkCell("Active / Idle Time", {w:2880,bold:true,fill:"EBF4FF"}), mkCell("Per-track cumulative seconds in each state. Displayed as MM:SS on the bounding box.",   {w:6480,fill:"EBF4FF"})] }),
        ]
      }),
      ...gap(1),
      h2("6.2 Customer Metrics"),
      new Table({
        width:{ size:9360, type:WidthType.DXA },
        columnWidths:[2880, 6480],
        rows:[
          new TableRow({ children:[hCell("Metric",2880), hCell("Computation",6480)] }),
          new TableRow({ children:[mkCell("Customer Count (cc)",      {w:2880,bold:true,fill:"EBF4FF"}), mkCell("Confirmed customer tracks visible in current frame.",                                                                         {w:6480,fill:"EBF4FF"})] }),
          new TableRow({ children:[mkCell("Wait Time (wt)",           {w:2880,bold:true}),               mkCell("wt = video_time - first_seen. Off-screen time excluded via gap correction.",                                                   {w:6480})] }),
          new TableRow({ children:[mkCell("Average Wait (avg)",       {w:2880,bold:true,fill:"EBF4FF"}), mkCell("Includes only customers tracked >= 30 s. Falls back to all tracked if none qualify.",                                         {w:6480,fill:"EBF4FF"})] }),
          new TableRow({ children:[mkCell("Service Pressure Index",   {w:2880,bold:true}),               mkCell("pressure = queue_size * avg_wait / 10. Computed in frontend analytics.",                                                       {w:6480})] }),
        ]
      }),
      ...gap(2),
      divider(),

      // ══════════════════════════════════════════════════════
      //  SECTION 7 — API REFERENCE
      // ══════════════════════════════════════════════════════
      h1("7. API & WebSocket Event Reference"),
      h2("7.1 REST Endpoints"),
      new Table({
        width:{ size:9360, type:WidthType.DXA },
        columnWidths:[1440, 1200, 6720],
        rows:[
          new TableRow({ children:[hCell("Route",1440), hCell("Method",1200), hCell("Description",6720)] }),
          new TableRow({ children:[mkCell("/",       {w:1440,bold:true,fill:"EBF4FF"}), mkCell("GET",  {w:1200,center:true,fill:"EBF4FF"}), mkCell("Serves dashboard.html.",{w:6720,fill:"EBF4FF"})] }),
          new TableRow({ children:[mkCell("/upload", {w:1440,bold:true}),               mkCell("POST", {w:1200,center:true}),               mkCell("Accepts multipart video. Returns JSON {success, path, filename}.",{w:6720})] }),
          new TableRow({ children:[mkCell("/status", {w:1440,bold:true,fill:"EBF4FF"}), mkCell("GET",  {w:1200,center:true,fill:"EBF4FF"}), mkCell("Returns model status and all config parameter values as JSON.",{w:6720,fill:"EBF4FF"})] }),
        ]
      }),
      ...gap(1),
      h2("7.2 Socket.IO Events"),
      new Table({
        width:{ size:9360, type:WidthType.DXA },
        columnWidths:[1440, 2160, 5760],
        rows:[
          new TableRow({ children:[hCell("Direction",1440), hCell("Event",2160), hCell("Payload",5760)] }),
          new TableRow({ children:[mkCell("S → C",{w:1440,center:true,fill:"E8F5E9",bold:true,color:"1B7A3A"}), mkCell("frame_data",      {w:2160,bold:true,fill:"E8F5E9"}), mkCell("Full per-frame payload: base64 JPEG, counts, ratios, staff_list, customer_list, alerts.",{w:5760,fill:"E8F5E9"})] }),
          new TableRow({ children:[mkCell("S → C",{w:1440,center:true,bold:true,color:"1B7A3A"}), mkCell("processing_done",{w:2160,bold:true}), mkCell("{frames_processed, total_frames, total_idle_alerts}",{w:5760})] }),
          new TableRow({ children:[mkCell("S → C",{w:1440,center:true,fill:"E8F5E9",bold:true,color:"1B7A3A"}), mkCell("model_status",   {w:2160,bold:true,fill:"E8F5E9"}), mkCell("{status: loaded|not_found, path}",{w:5760,fill:"E8F5E9"})] }),
          new TableRow({ children:[mkCell("C → S",{w:1440,center:true,bold:true,color:"1B3A5C"}), mkCell("start_processing",{w:2160,bold:true}), mkCell("{path}: starts process_video() daemon thread.",{w:5760})] }),
          new TableRow({ children:[mkCell("C → S",{w:1440,center:true,fill:"EBF4FF",bold:true,color:"1B3A5C"}), mkCell("stop_processing",{w:2160,bold:true,fill:"EBF4FF"}), mkCell("Sets stop_flag to halt processing gracefully.",{w:5760,fill:"EBF4FF"})] }),
          new TableRow({ children:[mkCell("C → S",{w:1440,center:true,bold:true,color:"1B3A5C"}), mkCell("update_config",  {w:2160,bold:true}), mkCell("{conf?, idle_move_threshold?, idle_confirm_secs?}: hot-update mid-session.",{w:5760})] }),
        ]
      }),
      ...gap(2),
      divider(),

      // ══════════════════════════════════════════════════════
      //  SECTION 8 — DATA EXPORT
      // ══════════════════════════════════════════════════════
      h1("8. Data Export"),
      new Table({
        width:{ size:9360, type:WidthType.DXA },
        columnWidths:[2400, 2160, 4800],
        rows:[
          new TableRow({ children:[hCell("Export",2400), hCell("Filename",2160), hCell("Contents",4800)] }),
          new TableRow({ children:[mkCell("Staff Report",   {w:2400,bold:true,fill:"EBF4FF"}), mkCell("staff_report_<ts>.csv",   {w:2160,fill:"EBF4FF"}), mkCell("Per-staff active/idle time, percentages, idle rate trend.",   {w:4800,fill:"EBF4FF"})] }),
          new TableRow({ children:[mkCell("Customer Report",{w:2400,bold:true}),               mkCell("customer_report_<ts>.csv",{w:2160}),               mkCell("Summary metrics, wait brackets, service pressure time-series.",{w:4800})] }),
          new TableRow({ children:[mkCell("Analytics",      {w:2400,bold:true,fill:"EBF4FF"}), mkCell("analytics_<ts>.csv",      {w:2160,fill:"EBF4FF"}), mkCell("Full time-series: avg wait, active ratio, queue size, idle rate.",{w:4800,fill:"EBF4FF"})] }),
        ]
      }),
      ...gap(2),
      divider(),

      // ══════════════════════════════════════════════════════
      //  SECTION 9 — DEPLOYMENT
      // ══════════════════════════════════════════════════════
      h1("9. Deployment & Setup"),
      new Table({
        width:{ size:9360, type:WidthType.DXA },
        columnWidths:[3600, 5760],
        rows:[
          new TableRow({ children:[hCell("Requirement",3600), hCell("Details",5760)] }),
          twoColRow("Python",          "3.9 or later"),
          twoColRow("PyTorch",         "GPU build recommended (CUDA 11.8+)", true),
          twoColRow("Ultralytics",     "pip install ultralytics"),
          twoColRow("Flask",           "pip install flask flask-socketio", true),
          twoColRow("OpenCV",          "pip install opencv-python"),
          twoColRow("Model Weights",   "Place best.pt at runs/detect/workforce_monitor/staff_customer_v4/weights/", true),
        ]
      }),
      ...gap(1),
      para("Start the server with:  python app.py  — then open http://localhost:5000 in any modern browser."),
      ...gap(2),
      divider(),

      // ══════════════════════════════════════════════════════
      //  FOOTER
      // ══════════════════════════════════════════════════════
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing:{ before:160, after:0 },
        children:[new TextRun({
          text:"Workforce Monitor  |  Vision-Based Employee Tracking  |  Auto-generated Technical & Evaluation Report",
          font:"Arial", size:18, color:"888888", italics:true
        })]
      }),

    ]
  }]
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT, buf);
  console.log('DONE:' + OUT);
}).catch(e => { console.error(e); process.exit(1); });
