import { useState, useEffect } from "react";

const MODULES = [
  {
    id: 1, title: "Pattern Rules", icon: "📐", time: "45 min", level: "All",
    sections: [
      { title: "Why Patterns Matter", content: "The best FRC teams don't start from scratch every year. They apply design patterns — proven approaches that worked across multiple seasons, multiple games, and multiple teams. We studied 13 championship-winning teams across 10 seasons (2016–2025) and extracted 17 rules + 10 meta-rules they follow." },
      { title: "The Teams We Study", content: "254 Cheesy Poofs (8× World Champs), 118 Robonauts (NASA-backed + Everybot), 1678 Citrus Circuits (scouting + strategy), 6328 Mechanical Advantage (AdvantageKit), 3847 Spectrum (build blog + guidelines), 1323 MadTown (2025 World Champs), 4414 HighTide (simple & rigid), 2056 OP Robotics (engineering drawings), 1690 Orbit (software sophistication), 2910 Jack in the Bot (swerve pioneers), 1114 Simbotics (code templates), 973 Greybots (subsystem examples), 2826 Wave Robotics (YOLO models)." },
      { title: "Core Rules", content: "Rule 1: Swerve drive always (100% confidence). Rule 2: Full-width intake (95%). Rule 3: Match roller material to game piece. Rule 4: Flywheel for throwing, elevator+wrist for placing. Rule 5: Elevator stages by height needed. Rule 6: Turret only when aiming while driving. Rule 7: Climb mandatory when >15% of winning score." },
      { title: "Software & Strategy Rules", content: "Rule 11: Cycle speed above all else — champions are 0.5–1.0s faster per cycle. Rule 14: State machine + vision + logging. Rule 16: For dual game pieces, build ONE mechanism optimized for the higher-value piece. Rule 17: Intake on opposite end from scorer to eliminate 180° turns." },
      { title: "Meta-Rules", content: "M1: Simple beats complex when executed perfectly (4414). M2: Iteration speed > first design quality (254 V1→V2). M3: The team that drives more wins (50+ hours practice). M6: No pneumatics in 2026+ (20 motor slots). M7: Build multiple robots (254 AlphaBot, 3847 AM/XM/PM/FM). M10: Don't chase magic numbers — build in margins." },
    ],
    quiz: [
      { q: "Your alliance partner says 'let's build whatever scores the most points.' What's wrong with that thinking?", options: ["Nothing — points win matches", "Ranking Points determine your seed, not raw score", "Defense is more important", "You should build the climber first"], answer: 1 },
      { q: "A game has scoring locations 3 feet from the starting position. Should you gear your swerve for maximum speed?", options: ["Yes — faster is always better", "No — short distances favor acceleration over top speed", "It depends on the game piece", "Speed doesn't matter for swerve"], answer: 1 },
      { q: "You have 2 weeks left in build season. Add a second mechanism OR make your existing one 50% faster and 100% reliable?", options: ["Add the second mechanism for more versatility", "Make the existing mechanism faster and reliable", "Both — split the team", "Neither — focus on driver practice"], answer: 1 },
      { q: "Which team's philosophy is 'simple and rigid beats complex'?", options: ["254", "1678", "4414 HighTide", "6328"], answer: 2 },
      { q: "When should the climber be designed in the build season?", options: ["First — it's the hardest", "Week 1 alongside the drivetrain", "Last — after scoring is locked", "It depends on the game"], answer: 2 },
    ]
  },
  {
    id: 2, title: "Prediction Engine", icon: "🧠", time: "60 min", level: "All",
    sections: [
      { title: "What It Does", content: "The prediction engine takes a filled-in game analysis template and outputs mechanism recommendations with confidence scores. On kickoff day: watch the reveal, fill in the template, paste it with the pattern rules into Claude, and get a complete robot architecture in ~4 hours." },
      { title: "Utility Scoring", content: "Every possible action (SCORE, COLLECT, CLIMB, DEFEND) gets a utility score. Higher = better. The robot always picks the highest-utility action. Utility factors: base value of action, distance cost, fuel bonus (holding fuel near hub = high score utility), opponent penalty (opponent near target = lower utility), and time pressure (climb utility spikes in endgame)." },
      { title: "Bot Aborter", content: "Before committing to a target, check: will an opponent get there first? Formula: abort if (myDistance/mySpeed) - (oppDistance/oppSpeed) >= 0.75 seconds. If the opponent arrives 0.75+ seconds before us, abandon that target and pick the next-best option. This prevents wasted cycles." },
      { title: "The Decision Loop", content: "Every 0.5 seconds: 1) Build GameState (pose, fuel held, hub active, time, opponents). 2) Score all possible targets. 3) Pick highest utility. 4) Check Bot Aborter. 5) If target changed, re-plan path. 6) Execute. This runs continuously during autonomous AND can assist during teleop." },
      { title: "Validated Against REBUILT", content: "We ran the prediction engine against the 2026 REBUILT game manual and compared to what 254 (32-2, EPA 331.7) and 1323 (34-0, EPA 313.5) actually built. Result: ~92% accuracy on mechanism architecture. The engine correctly predicted: swerve + full-width intake + large hopper + turret + flywheel + multi-rung climber + ~115 lbs." },
    ],
    quiz: [
      { q: "The robot holds 5 fuel, the hub is active, and there's 60 seconds left. What action type likely has the highest utility?", options: ["COLLECT more fuel", "SCORE into the hub", "CLIMB the tower", "DEFEND an opponent"], answer: 1 },
      { q: "Your robot is 3.0m from a fuel ball at 3.0 m/s. An opponent is 1.0m away at 2.0 m/s. Should you abort? (threshold: 0.75s)", options: ["Yes — opponent arrives 0.5s sooner", "No — the difference (0.5s) is below the 0.75s threshold", "Yes — the opponent is closer", "Can't determine without more data"], answer: 1 },
      { q: "How often does the strategy re-evaluation cycle run?", options: ["Every robot loop (20ms)", "Every 0.5 seconds", "Once per autonomous period", "Only when a target is reached"], answer: 1 },
      { q: "What does 'retarget hysteresis' prevent?", options: ["The robot from moving too fast", "Rapid switching between targets when utilities are close", "Vision false positives", "Motor overheating"], answer: 1 },
      { q: "The prediction engine scored ~92% accuracy against REBUILT. What was the biggest uncertainty?", options: ["Drivetrain type", "Whether top teams use turrets", "The programming language", "Whether swerve works"], answer: 1 },
    ]
  },
  {
    id: 3, title: "Design Intelligence", icon: "🔬", time: "60 min", level: "Veterans",
    sections: [
      { title: "The Full Pipeline", content: "Kickoff day workflow: 1) Watch game reveal. 2) Fill in KICKOFF_TEMPLATE.md with game rules, field dimensions, game pieces, scoring methods, endgame. 3) Paste template + CROSS_SEASON_PATTERNS.md + TEAM_DATABASE.md into Claude. 4) Claude outputs mechanism recommendations. 5) Compare against brainstorming. 6) Start prototyping within 4 hours." },
      { title: "254 Undertow Deep Dive", content: "254's 2025 robot: WCP X2i swerve (13.2 ft/s), 18 motors total, 2-stage elevator (52\" in 0.3s), Flying V end effector for never-miss scoring, roller claw climber (1:224 gearbox), 2× Limelight 4 with heatsinks. Key lesson: intake direction opposite scoring side. AlphaBot built in 1 week using 2023 drivebase to learn gameplay before designing competition robot." },
      { title: "3847 Spectrum Guidelines", content: "The 'Don't Do' list: No pneumatics, no scissor lifts, no narrow intakes, no pink arms, no mecanum/tank, no small motors, no 6-32 bolts. Build process: AM (Alpha Machine, days 1-7) → XM (Experiment Machine) → PM (Provisional Machine, week 1 comp) → FM (Final Machine, after seeing real matches). 'Don't chase magic numbers' — build in margins." },
      { title: "Open Alliance Network", content: "60+ teams publish detailed build threads during the 2026 season. Key threads to monitor: 6328 (AdvantageKit creators), 2826 Wave Robotics (YOLO model source), 3847 Spectrum (process documentation), 4481 Team Rembrandts, 4590 GreenBlitz. The 2025 World Champions (1323) credited 3847 for their intake and 2910 for their climber. Elite teams learn from each other publicly." },
      { title: "Statbotics EPA", content: "EPA (Expected Points Added) predicts a team's scoring contribution per match. 2026 REBUILT: 254 has 331.7 total EPA (59.7 auto + 191.9 teleop + 80.1 endgame). 1323 has 313.5 EPA but is 34-0 undefeated. The 2× gap between 254/1323 (~192 teleop) and 118 (~94 teleop) suggests a fundamental mechanism capability difference — likely turret + hopper + shoot-on-move." },
    ],
    quiz: [
      { q: "What's the FIRST thing you do on kickoff day with the prediction engine?", options: ["Start building the drivetrain", "Watch the reveal and fill in KICKOFF_TEMPLATE.md", "Read last year's 254 binder", "Vote on robot design"], answer: 1 },
      { q: "254's AlphaBot 'Elphaba' was built in how long?", options: ["1 day", "1 week", "2 weeks", "1 month"], answer: 1 },
      { q: "1323 MadTown credited which team for their intake design?", options: ["254", "1678", "3847 Spectrum", "6328"], answer: 2 },
      { q: "What does EPA stand for?", options: ["Estimated Points Average", "Expected Points Added", "Engineering Performance Assessment", "Event Placement Algorithm"], answer: 1 },
      { q: "How many teams are in the 2026 Open Alliance directory?", options: ["~15", "~30", "~60+", "~200"], answer: 2 },
    ]
  },
  {
    id: 4, title: "Pathfinding", icon: "🗺️", time: "50 min", level: "All",
    sections: [
      { title: "Why Pathfinding?", content: "The robot knows WHERE it wants to go (the strategy picked a target). But the field isn't empty — walls, game elements, and opponents are in the way. The Engine uses 3 layers: Layer 1 (NavigationGrid) is the map, Layer 2 (A* Pathfinder) plans a route around obstacles, Layer 3 (DynamicAvoidanceLayer) adjusts in real-time when opponents move." },
      { title: "Navigation Grid", content: "The FRC field (16.54m × 8.21m) is divided into 164×82 cells, each 0.10m × 0.10m. Each cell is passable (0) or blocked (1). The grid loads from navgrid.json at startup. Coordinate conversion: field meters → grid cell = divide by 0.1. Grid cell → field meters = multiply by 0.1 + half cell for center." },
      { title: "A* Algorithm", content: "A* finds the shortest path using f = g + h. g = actual cost from start. h = estimated cost to goal (Euclidean distance). Explores lowest-f cells first via a priority queue. 8-directional movement: cardinal cost = 1.0, diagonal cost = √2 ≈ 1.41. Guaranteed optimal path because Euclidean heuristic is admissible (never overestimates)." },
      { title: "Dynamic Obstacles", content: "Static grid has walls and field elements. Opponents MOVE. Every 20ms cycle: clear old dynamic obstacles, stamp 0.8m × 0.8m bounding boxes at current opponent positions, then plan path on the updated grid. If robot drifts >0.30m from planned path, immediate re-plan." },
      { title: "Full Call Chain", content: "1) Strategy picks target. 2) Grid updated with opponent positions. 3) A* finds waypoints. 4) PathPlannerLib smooths them into a spline. 5) DynamicAvoidanceLayer adjusts velocity in real-time. Re-planning every 0.5s, immediately on Bot Aborter trigger, and on arrival at current target." },
    ],
    quiz: [
      { q: "An opponent is at field position (8.0, 3.0). With 0.1m cells, what grid cell is that?", options: ["(8, 3)", "(80, 30)", "(800, 300)", "(0.8, 0.3)"], answer: 1 },
      { q: "In A*, what does the heuristic (h) represent?", options: ["Actual cost from start", "Estimated cost to goal", "Total path cost", "Number of obstacles"], answer: 1 },
      { q: "Why does diagonal movement cost √2 instead of 1.0?", options: ["It's arbitrary", "Pythagorean theorem — diagonal of a unit square", "Diagonals are penalized to prefer straight lines", "It's a bug in the code"], answer: 1 },
      { q: "What happens if A* can't find a path to the goal?", options: ["The robot crashes", "Returns an empty list — caller falls back to a different target", "Tries again with a bigger grid", "Switches to random movement"], answer: 1 },
      { q: "How often are dynamic obstacles (opponent positions) updated?", options: ["Once per match", "Every 0.5 seconds", "Every robot loop cycle (~20ms)", "Only when opponents are detected"], answer: 2 },
    ]
  },
  {
    id: 5, title: "Vision & YOLO", icon: "👁️", time: "55 min", level: "All",
    sections: [
      { title: "The Vision Pipeline", content: "Camera frame → SnapScript on Limelight (YOLO inference at 30+ fps) → NMS + confidence filter ≥ 0.80 → pixel-to-field projection → NetworkTables array → FuelDetectionConsumer on roboRIO (3-frame persistence filter) → confirmed fuel positions for strategy and driving." },
      { title: "The YOLO Model", content: "Wave Robotics YOLOv11-nano: 2.59M parameters, 640×640 input, 1 class (fuel ball), 93-97% confidence on training data, 30+ fps on Limelight 4 Hailo accelerator. Already integrated — tools/wave_fuel_detector.onnx (10.1 MB). Trained on 60 labeled images by Team 2826." },
      { title: "Confidence & Persistence", content: "Two filter stages prevent false positives. Stage 1 (SnapScript): NMS with IoU 0.45, confidence ≥ 0.80. Stage 2 (Java): 80% secondary gate + 3-frame persistence (detection must appear in same location for 3 consecutive frames). Max 8 simultaneous detections." },
      { title: "Pixel to Field Conversion", content: "Raw detections are in pixel coordinates (cx, cy in 640×480 image). Camera geometry (height, pitch, FOV) + robot pose (from odometry) converts to field-relative meters (x, y on the field map). This feeds directly into the pathfinding system — detected fuel becomes a COLLECT target with known field position." },
      { title: "Dual Camera Strategy", content: "Limelight 1: AprilTag pipeline for pose estimation (localization). Limelight 2: YOLO pipeline for game piece detection. Pipeline switching: during auto, both cameras active. During teleop, pose estimation runs continuously while game piece detection activates on driver request or near collection zones." },
    ],
    quiz: [
      { q: "How many consecutive frames must a detection appear before it's confirmed?", options: ["1 (immediate)", "2 frames", "3 frames", "5 frames"], answer: 2 },
      { q: "What's the confidence threshold for the YOLO model on the SnapScript?", options: ["50%", "70%", "80%", "95%"], answer: 2 },
      { q: "The Wave Robotics YOLO model detects fuel balls. Does it also detect opponent robots?", options: ["Yes — it has 2 classes", "No — opponent avoidance uses a different data source", "Yes — via a separate pipeline", "No — opponents can't be detected"], answer: 1 },
      { q: "What hardware runs the YOLO inference?", options: ["The roboRIO", "A Raspberry Pi", "The Limelight 4 with Hailo accelerator", "A Jetson Nano"], answer: 2 },
      { q: "If the YOLO model fails to load on the Limelight, what happens?", options: ["The robot can't detect fuel", "An HSV color fallback activates automatically", "The match is forfeit", "The driver must manually aim"], answer: 1 },
    ]
  },
  {
    id: 6, title: "Simulation & Testing", icon: "🧪", time: "55 min", level: "All",
    sections: [
      { title: "The 4 Quality Gates", content: "Every build runs 4 checks: Spotless (auto-formats code), SpotBugs (finds bug patterns without running code), JUnit (runs 246+ tests), JaCoCo (measures test coverage — frc.lib must be ≥80%). If ANY gate fails, the build fails. This catches problems before they reach the robot." },
      { title: "Writing Tests (AAA Pattern)", content: "Every test follows Arrange-Act-Assert: ARRANGE sets up the scenario (create objects, configure state). ACT runs the code being tested (call a method). ASSERT checks the result (assertEquals, assertTrue, assertNotNull). Tests must be HAL-free — no hardware imports, no Constants references that touch hardware." },
      { title: "Simulation", content: "Run ./gradlew simulateJava to launch. maple-sim provides swerve physics (motor forces, friction, collisions). AdvantageScope connects to localhost:3300 for live visualization. You can run autonomous, teleop, or disabled mode. Every subsystem logs to AdvantageKit — replay any match later." },
      { title: "The maple-sim Bug", content: "maple-sim 0.4.0-beta has an upstream bug: motor forces are inverted for REV SPARK MAX/NEO hardware. We implemented a kinematic bypass for both driveRobotRelative() and drive() methods. The fix works but the robot won't have accurate force-based physics until the upstream fix. Bug report drafted in MAPLE_SIM_BUG_REPORT.md." },
      { title: "Competition Data Collection", content: "At every event: 1) Save match logs from AdvantageKit (USB stick in roboRIO). 2) Run post-match analysis scripts. 3) Record cycle times from CycleTracker. 4) Note any mechanism failures in Robot Reports channel. 5) Compare predicted vs actual autonomous performance. This data feeds back into pattern rules for next season." },
    ],
    quiz: [
      { q: "Which quality gate auto-formats your code?", options: ["SpotBugs", "Spotless", "JaCoCo", "JUnit"], answer: 1 },
      { q: "What does AAA stand for in test writing?", options: ["Automate-Analyze-Assert", "Arrange-Act-Assert", "Apply-Assess-Adjust", "Activate-Attempt-Approve"], answer: 1 },
      { q: "What minimum test coverage is required for frc.lib?", options: ["50%", "70%", "80%", "95%"], answer: 2 },
      { q: "You add 'String s = null; s.length();' to a method. Which gate catches it?", options: ["Spotless", "SpotBugs", "JUnit", "JaCoCo"], answer: 1 },
      { q: "How do you connect AdvantageScope to the simulation?", options: ["USB cable to robot", "Connect to localhost:3300", "Deploy code first", "Open a .wpilog file"], answer: 1 },
    ]
  },
];

const BADGES = [
  { min: 0, max: 9, name: "Observer", emoji: "👀", desc: "Keep learning!" },
  { min: 10, max: 19, name: "Apprentice", emoji: "🔧", desc: "Contribute with guidance" },
  { min: 20, max: 24, name: "Operator", emoji: "⚙️", desc: "Contribute independently" },
  { min: 25, max: 30, name: "Engine Master", emoji: "🏆", desc: "Ready to lead a subsystem" },
];

function getBadge(score) {
  return BADGES.find(b => score >= b.min && score <= b.max) || BADGES[0];
}

export default function TrainingApp() {
  const [view, setView] = useState("home");
  const [currentModule, setCurrentModule] = useState(null);
  const [currentSection, setCurrentSection] = useState(0);
  const [quizMode, setQuizMode] = useState(false);
  const [quizAnswers, setQuizAnswers] = useState({});
  const [quizSubmitted, setQuizSubmitted] = useState(false);
  const [completedModules, setCompletedModules] = useState({});
  const [totalScore, setTotalScore] = useState(0);

  const startModule = (mod) => {
    setCurrentModule(mod);
    setCurrentSection(0);
    setQuizMode(false);
    setQuizAnswers({});
    setQuizSubmitted(false);
    setView("module");
  };

  const submitQuiz = () => {
    if (!currentModule) return;
    let correct = 0;
    currentModule.quiz.forEach((q, i) => {
      if (quizAnswers[i] === q.answer) correct++;
    });
    setQuizSubmitted(true);
    const newCompleted = { ...completedModules, [currentModule.id]: correct };
    setCompletedModules(newCompleted);
    setTotalScore(Object.values(newCompleted).reduce((a, b) => a + b, 0));
  };

  const badge = getBadge(totalScore);

  if (view === "home") {
    return (
      <div style={{ minHeight: "100vh", background: "linear-gradient(135deg, #0a0a1a 0%, #1a1a3e 50%, #0d1b2a 100%)", fontFamily: "'Segoe UI', system-ui, sans-serif", color: "#e0e0e0", padding: "0" }}>
        <div style={{ maxWidth: 900, margin: "0 auto", padding: "2rem 1.5rem" }}>
          <div style={{ textAlign: "center", marginBottom: "2.5rem" }}>
            <div style={{ fontSize: "3rem", fontWeight: 800, background: "linear-gradient(90deg, #00d4ff, #7b2ff7, #ff6b6b)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", letterSpacing: "-1px" }}>THE ENGINE</div>
            <div style={{ fontSize: "1.1rem", color: "#8899aa", marginTop: "0.3rem", letterSpacing: "3px", textTransform: "uppercase" }}>Student Training Platform</div>
            <div style={{ fontSize: "0.85rem", color: "#556677", marginTop: "0.5rem" }}>Team 2950 — The Devastators</div>
          </div>

          {totalScore > 0 && (
            <div style={{ background: "rgba(123,47,247,0.12)", border: "1px solid rgba(123,47,247,0.3)", borderRadius: 12, padding: "1rem 1.5rem", marginBottom: "2rem", display: "flex", alignItems: "center", gap: "1rem" }}>
              <span style={{ fontSize: "2.5rem" }}>{badge.emoji}</span>
              <div>
                <div style={{ fontWeight: 700, fontSize: "1.1rem", color: "#c4a0ff" }}>{badge.name}</div>
                <div style={{ fontSize: "0.85rem", color: "#8899aa" }}>{totalScore}/30 points — {badge.desc}</div>
              </div>
              <div style={{ marginLeft: "auto", width: 120, height: 8, background: "rgba(255,255,255,0.1)", borderRadius: 4, overflow: "hidden" }}>
                <div style={{ width: `${(totalScore / 30) * 100}%`, height: "100%", background: "linear-gradient(90deg, #7b2ff7, #00d4ff)", borderRadius: 4, transition: "width 0.5s ease" }} />
              </div>
            </div>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "1rem" }}>
            {MODULES.map(mod => {
              const done = completedModules[mod.id] !== undefined;
              const score = completedModules[mod.id] || 0;
              return (
                <div key={mod.id} onClick={() => startModule(mod)} style={{ background: done ? "rgba(0,212,255,0.08)" : "rgba(255,255,255,0.04)", border: `1px solid ${done ? "rgba(0,212,255,0.3)" : "rgba(255,255,255,0.08)"}`, borderRadius: 12, padding: "1.25rem", cursor: "pointer", transition: "all 0.2s ease", position: "relative" }}
                  onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.borderColor = "rgba(0,212,255,0.5)"; }}
                  onMouseLeave={e => { e.currentTarget.style.transform = ""; e.currentTarget.style.borderColor = done ? "rgba(0,212,255,0.3)" : "rgba(255,255,255,0.08)"; }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.75rem" }}>
                    <span style={{ fontSize: "1.8rem" }}>{mod.icon}</span>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: "1rem", color: "#fff" }}>Module {mod.id}</div>
                      <div style={{ fontSize: "0.8rem", color: "#667788" }}>{mod.time} · {mod.level}</div>
                    </div>
                    {done && <span style={{ marginLeft: "auto", color: "#00d4ff", fontSize: "1.2rem" }}>✓</span>}
                  </div>
                  <div style={{ fontSize: "0.95rem", fontWeight: 600, color: done ? "#00d4ff" : "#ccd" }}>{mod.title}</div>
                  {done && <div style={{ fontSize: "0.75rem", color: "#8899aa", marginTop: "0.4rem" }}>{score}/5 correct</div>}
                </div>
              );
            })}
          </div>

          <div style={{ marginTop: "2.5rem", padding: "1.25rem", background: "rgba(255,255,255,0.03)", borderRadius: 12, border: "1px solid rgba(255,255,255,0.06)" }}>
            <div style={{ fontWeight: 700, fontSize: "1rem", color: "#aabbcc", marginBottom: "0.5rem" }}>Recommended Path</div>
            <div style={{ fontSize: "0.85rem", color: "#778899", lineHeight: 1.7 }}>
              <strong style={{ color: "#ccd" }}>Week 1:</strong> Modules 1 (Patterns) → 2 (Prediction Engine) → Onboarding exercises<br />
              <strong style={{ color: "#ccd" }}>Week 2:</strong> Modules 3 (Design Intelligence) → 4 (Pathfinding) → 5 (Vision)<br />
              <strong style={{ color: "#ccd" }}>Week 3:</strong> Module 6 (Sim & Testing) → Simulation exercise sets → Write 3 new tests
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (view === "module" && currentModule) {
    const mod = currentModule;
    const section = mod.sections[currentSection];

    if (quizMode) {
      return (
        <div style={{ minHeight: "100vh", background: "linear-gradient(135deg, #0a0a1a 0%, #1a1a3e 50%, #0d1b2a 100%)", fontFamily: "'Segoe UI', system-ui, sans-serif", color: "#e0e0e0", padding: "0" }}>
          <div style={{ maxWidth: 700, margin: "0 auto", padding: "2rem 1.5rem" }}>
            <button onClick={() => { setQuizMode(false); setCurrentSection(mod.sections.length - 1); }} style={{ background: "none", border: "1px solid rgba(255,255,255,0.15)", color: "#8899aa", padding: "0.4rem 1rem", borderRadius: 6, cursor: "pointer", marginBottom: "1.5rem", fontSize: "0.85rem" }}>← Back to content</button>
            <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "#fff", marginBottom: "0.3rem" }}>{mod.icon} Module {mod.id} Quiz</div>
            <div style={{ fontSize: "0.85rem", color: "#667788", marginBottom: "2rem" }}>5 questions · Select the best answer</div>

            {mod.quiz.map((q, qi) => {
              const answered = quizAnswers[qi] !== undefined;
              const correct = quizSubmitted && quizAnswers[qi] === q.answer;
              const wrong = quizSubmitted && answered && quizAnswers[qi] !== q.answer;
              return (
                <div key={qi} style={{ marginBottom: "1.5rem", padding: "1.25rem", background: quizSubmitted ? (correct ? "rgba(0,200,100,0.08)" : wrong ? "rgba(255,80,80,0.08)" : "rgba(255,255,255,0.03)") : "rgba(255,255,255,0.03)", border: `1px solid ${quizSubmitted ? (correct ? "rgba(0,200,100,0.3)" : wrong ? "rgba(255,80,80,0.3)" : "rgba(255,255,255,0.06)") : "rgba(255,255,255,0.06)"}`, borderRadius: 10 }}>
                  <div style={{ fontWeight: 600, fontSize: "0.95rem", color: "#dde", marginBottom: "0.75rem" }}>{qi + 1}. {q.q}</div>
                  {q.options.map((opt, oi) => {
                    const selected = quizAnswers[qi] === oi;
                    const isCorrect = quizSubmitted && oi === q.answer;
                    return (
                      <div key={oi} onClick={() => !quizSubmitted && setQuizAnswers({ ...quizAnswers, [qi]: oi })} style={{ padding: "0.6rem 1rem", marginBottom: "0.4rem", borderRadius: 6, cursor: quizSubmitted ? "default" : "pointer", background: selected ? "rgba(123,47,247,0.2)" : "rgba(255,255,255,0.02)", border: `1px solid ${isCorrect && quizSubmitted ? "rgba(0,200,100,0.5)" : selected ? "rgba(123,47,247,0.4)" : "rgba(255,255,255,0.06)"}`, fontSize: "0.88rem", color: isCorrect && quizSubmitted ? "#6fdf8f" : selected ? "#c4a0ff" : "#aab", transition: "all 0.15s ease" }}>
                        {opt}
                        {quizSubmitted && isCorrect && " ✓"}
                        {quizSubmitted && selected && !isCorrect && " ✗"}
                      </div>
                    );
                  })}
                </div>
              );
            })}

            {!quizSubmitted ? (
              <button onClick={submitQuiz} disabled={Object.keys(quizAnswers).length < 5} style={{ width: "100%", padding: "0.85rem", borderRadius: 8, border: "none", background: Object.keys(quizAnswers).length < 5 ? "rgba(255,255,255,0.05)" : "linear-gradient(90deg, #7b2ff7, #00d4ff)", color: Object.keys(quizAnswers).length < 5 ? "#556" : "#fff", fontWeight: 700, fontSize: "1rem", cursor: Object.keys(quizAnswers).length < 5 ? "not-allowed" : "pointer" }}>
                {Object.keys(quizAnswers).length < 5 ? `Answer all questions (${Object.keys(quizAnswers).length}/5)` : "Submit Quiz"}
              </button>
            ) : (
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: "2rem", fontWeight: 800, color: "#fff", marginBottom: "0.5rem" }}>{completedModules[mod.id]}/5</div>
                <div style={{ fontSize: "0.9rem", color: "#8899aa", marginBottom: "1rem" }}>{completedModules[mod.id] >= 4 ? "Excellent work!" : completedModules[mod.id] >= 3 ? "Good job — review the ones you missed." : "Review the module content and try again."}</div>
                <button onClick={() => setView("home")} style={{ padding: "0.7rem 2rem", borderRadius: 8, border: "none", background: "linear-gradient(90deg, #7b2ff7, #00d4ff)", color: "#fff", fontWeight: 700, cursor: "pointer" }}>Back to Dashboard</button>
              </div>
            )}
          </div>
        </div>
      );
    }

    return (
      <div style={{ minHeight: "100vh", background: "linear-gradient(135deg, #0a0a1a 0%, #1a1a3e 50%, #0d1b2a 100%)", fontFamily: "'Segoe UI', system-ui, sans-serif", color: "#e0e0e0", padding: "0" }}>
        <div style={{ maxWidth: 700, margin: "0 auto", padding: "2rem 1.5rem" }}>
          <button onClick={() => setView("home")} style={{ background: "none", border: "1px solid rgba(255,255,255,0.15)", color: "#8899aa", padding: "0.4rem 1rem", borderRadius: 6, cursor: "pointer", marginBottom: "1.5rem", fontSize: "0.85rem" }}>← All Modules</button>

          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.3rem" }}>
            <span style={{ fontSize: "2rem" }}>{mod.icon}</span>
            <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "#fff" }}>Module {mod.id}: {mod.title}</div>
          </div>
          <div style={{ fontSize: "0.85rem", color: "#667788", marginBottom: "1.5rem" }}>{mod.time} · {mod.level} · Section {currentSection + 1} of {mod.sections.length}</div>

          <div style={{ display: "flex", gap: 4, marginBottom: "1.5rem" }}>
            {mod.sections.map((_, i) => (
              <div key={i} onClick={() => setCurrentSection(i)} style={{ flex: 1, height: 4, borderRadius: 2, background: i <= currentSection ? "linear-gradient(90deg, #7b2ff7, #00d4ff)" : "rgba(255,255,255,0.1)", cursor: "pointer", transition: "background 0.3s" }} />
            ))}
          </div>

          <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12, padding: "1.5rem", marginBottom: "1.5rem", minHeight: 200 }}>
            <div style={{ fontSize: "1.15rem", fontWeight: 700, color: "#00d4ff", marginBottom: "1rem" }}>{section.title}</div>
            <div style={{ fontSize: "0.92rem", lineHeight: 1.8, color: "#bcc8d8", whiteSpace: "pre-wrap" }}>{section.content}</div>
          </div>

          <div style={{ display: "flex", gap: "0.75rem" }}>
            {currentSection > 0 && (
              <button onClick={() => setCurrentSection(currentSection - 1)} style={{ flex: 1, padding: "0.7rem", borderRadius: 8, border: "1px solid rgba(255,255,255,0.15)", background: "none", color: "#8899aa", fontWeight: 600, cursor: "pointer" }}>← Previous</button>
            )}
            {currentSection < mod.sections.length - 1 ? (
              <button onClick={() => setCurrentSection(currentSection + 1)} style={{ flex: 1, padding: "0.7rem", borderRadius: 8, border: "none", background: "linear-gradient(90deg, #7b2ff7, #00d4ff)", color: "#fff", fontWeight: 700, cursor: "pointer" }}>Next Section →</button>
            ) : (
              <button onClick={() => setQuizMode(true)} style={{ flex: 1, padding: "0.7rem", borderRadius: 8, border: "none", background: "linear-gradient(90deg, #ff6b6b, #ff9a56)", color: "#fff", fontWeight: 700, cursor: "pointer" }}>Take Quiz 🎯</button>
            )}
          </div>
        </div>
      </div>
    );
  }

  return null;
}
