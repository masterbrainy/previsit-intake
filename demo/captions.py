"""Every on-screen caption in the demo video. Test & Support reviews each claim against the code (PROGRESS D.6).

Each caption: (scene label, what is happening, safety rule shown or "").
"""

INTRO_TITLE = "Pre-visit intake: prototype walkthrough"
INTRO_LINES = (
    "Recorded automatically from the running prototype, with a synthetic patient.",
    "The patient's typed answers come from a scripted case played by a second AI.",
    "Not for clinical use. Clinical content is a draft pending clinician sign-off.",
)
PAUSES_NOTE = "Synthetic patients · pauses while the AI responds are shortened"

BOOKING = ("1 · Booking", "The physician books an appointment. The system creates a private link for the patient.", "")
OPEN_LINK = (
    "1 · Booking",
    "The patient opens the private link. In a pilot it would arrive by SMS; SMS is not connected in this prototype.",
    "",
)
CONSENT = (
    "2 · Intake",
    "The assistant explains it is automated, not a doctor, that the call is recorded and shared, and asks for consent.",
    "",
)
IDENTITY = ("2 · Intake", "Identity check: the name and date of birth must match the booking before any history is taken.", "")
INTERVIEW = (
    "2 · Intake",
    "Adaptive history taking: each answer is checked for red-flag symptoms first, then the next question is chosen.",
    "Every patient turn is screened for emergencies before the interview continues",
)
FAST_FORWARD = (
    "2 · Intake",
    "Fast-forward ×4 (speech muted): the interview continues through the remaining history sections and the red-flag screen.",
    "Every patient turn is screened for emergencies before the interview continues",
)
READBACK = ("2 · Intake", "Read-back: the assistant summarises the main points and asks the patient to correct anything.", "")
ADVICE = (
    "2 · Intake",
    "General self-care advice, chosen only from a clinician-authored library, ending with when to go to the emergency department.",
    "No diagnosis, no medication advice",
)
DASHBOARD = ("3 · History sheet", "The physician's dashboard shows the intake is complete.", "")
SHEET = (
    "3 · History sheet",
    "The history sheet follows the standard structure: chief complaints in order of onset, HOPI, past, treatment, family and personal history.",
    "",
)
CITATION = (
    "3 · History sheet",
    "Every line cites the transcript turn it came from. Clicking a citation jumps to the patient's own words.",
    "Statements without a valid citation are dropped automatically",
)
SCREEN = ("3 · History sheet", "The red-flag screen and anything the patient could not answer are listed explicitly.", "")
SUGGESTED = (
    "4 · Approval gate",
    "A suggested test (CBC) with its rationale and the module rule that produced it. Only the physician sees this.",
    "Nothing medical reaches the patient without physician approval",
)
PATIENT_NOTHING = ("4 · Approval gate", "The patient's page shows no test: suggestions are invisible to patients.", "")
APPROVED = (
    "4 · Approval gate",
    "The physician approves. The patient still sees nothing until the physician also presses send.",
    "There is no auto-approval and no approval on timeout",
)
SENT = ("4 · Approval gate", "After the physician sends it, the patient sees the test and its instructions.", "")
TEMPS = (
    "5 · Symptom log",
    "The patient logs a temperature. The two earlier readings were pre-entered (backdated) for this demo.",
    "",
)
TEMPS_DOCTOR = ("5 · Symptom log", "The physician sees the readings as a table and chart on the patient's page.", "")
UPLOAD = ("6 · Lab result", "The patient uploads the lab report (a synthetic image).", "")
RESULT = (
    "6 · Lab result",
    "The physician sees the report exactly as issued, and is alerted that it arrived.",
    "Results are never sent to the AI and never interpreted by it",
)
RED_OPEN = ("7 · Red-flag stop", "A second synthetic patient starts their intake.", "")
RED_INTERVIEW = (
    "7 · Red-flag stop",
    "The patient describes their symptoms. Each answer is screened for emergency signs first.",
    "Every patient turn is screened for emergencies before the interview continues",
)
RED_STOP = (
    "7 · Red-flag stop",
    "Fever with a stiff neck is a red flag: the intake stops and the patient is told to seek emergency care now.",
    "Red flags stop the intake; the escalation wording is fixed, not AI-written",
)
RED_STAFF = (
    "7 · Red-flag stop",
    "Clinic staff are alerted immediately. The partial sheet is marked INTAKE STOPPED, and no advice or tests are generated.",
    "",
)
RED_PATIENT = ("7 · Red-flag stop", "The patient's page shows only the emergency instruction.", "")

LIMITS_TITLE = "Limits of this prototype"
LIMITS_LINES = (
    "Clinical content (red flags, fever module, advice library, test rules) is a DRAFT pending clinician sign-off.",
    "Safety evaluation on {n_scenarios} simulated cases: red-flag recall {recall}; key-fact accuracy {accuracy} (target 90%); "
    "fabricated facts {fabricated} (target 0).",
    "One shared physician login; no individual accounts yet.",
    "Browser channel only: no phone calls or SMS yet.",
    "Synthetic patients only. Not for clinical use.",
)
