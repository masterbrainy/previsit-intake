"""Every word on screen in the PATH demo film (demo/record.py). Test & Support reviews each claim against the code.

A caption is (chapter chip, what is happening, safety rule or ""). Cards are shown full screen between chapters.
"""

TITLE = {
    "kicker": "PATH · pre-visit intake",
    "title": "The history is taken <em>before</em> the patient walks in.",
    "lede": "PATH is a voice assistant that takes a patient's history at home and hands the doctor a structured, "
            "cited history sheet. No test or medical recommendation reaches the patient without the doctor's approval.",
}

CHAPTERS = {
    1: {"num": 1, "title": "The patient books", "lede": "Online, in a minute. PATH suggests doctors from what the patient types."},
    2: {"num": 2, "title": "The pre-visit call", "lede": "At home, before the visit, PATH takes the full history by voice."},
    3: {"num": 3, "title": "The doctor reviews", "lede": "Each doctor sees only their own patients, with the history ready."},
    4: {"num": 4, "title": "The safety net", "lede": "Red-flag symptoms stop the call and send the patient to emergency care."},
}

C1 = "01 · Patient books"
SIGN_IN = (C1, "The patient signs in with just a phone number and a one-time code.", "")
DETAILS = (C1, "First visit? They add their details once.", "")
REASON = (C1, "They say what the visit is about.", "")
RECOMMEND = (C1, "PATH suggests doctors from the words typed, using simple rules, not AI, and shows why. The patient picks a doctor and a time.", "")
BOOKED = (C1, "The booking appears on the hospital's overview straight away.", "")

C2 = "02 · Pre-visit call"
CONSENT = (C2, "PATH introduces itself as an automated assistant, not a doctor, and asks for consent.", "")
IDENTITY = (C2, "Fast-forward: PATH checks the name and date of birth against the booking.", "")
INTERVIEW = (C2, "Then it takes the history, choosing each question from the last answer.",
             "Every answer is screened for emergency signs first")
FAST_FORWARD = (C2, "Fast-forward: symptoms, past illnesses, medicines, allergies, family and social history.",
                "Every answer is screened for emergency signs first")
READBACK = (C2, "PATH reads back the main points so the patient can correct anything.", "")
ADVICE = (C2, "The call ends with general self-care advice and clear signs to seek urgent care.",
          "No diagnosis. No prescribing. No dosing.")

C3 = "03 · Doctor reviews"
DOCTOR_SIGN_IN = (C3, "Dr. Rao signs in to a personal account with a one-time code.", "")
MY_PATIENTS = (C3, "Only patients booked with Dr. Rao, or referred to Dr. Rao by another doctor, appear here.", "")
SHEET = (C3, "The history sheet is ready before the visit: complaints in order, history, medicines and allergies.", "")
CITATION = (C3, "Every line links back to the patient's own words in the transcript.", "Statements without a source are dropped")
SUGGESTED = (C3, "PATH suggests investigations, with the reason, to the doctor only.",
             "No test reaches the patient without the doctor's approval")
PATIENT_WAITS = (C3, "The patient has the self-care advice, but no test yet.", "")
APPROVE = (C3, "The doctor approves the test and sends it.", "No auto-approval, ever")
SENT = (C3, "Only now does the test, with its instructions, appear on the patient's phone.", "")

C4 = "04 · Safety net"
RED_START = (C4, "Another patient starts a pre-visit call.", "")
RED_FAST_FORWARD = (C4, "Fast-forward: consent and identity check.", "")
RED_INTERVIEW = (C4, "Each answer is checked for emergency signs before the next question.",
                 "Every answer is screened for emergency signs first")
RED_STOP = (C4, "Fever with a stiff neck is a red flag. PATH stops and gives fixed emergency instructions.",
            "Emergency wording is fixed, never written by AI")
RED_ALERT = (C4, "An emergency alert appears on the hospital overview at once, with the patient's contact details.", "")

END = {
    "kicker": "PATH",
    "title": "Better first visits, <em>safely</em>.",
    "lines": [
        ("01", "The history is taken at home, by voice, before the visit."),
        ("02", "Doctors get a structured, cited history sheet and suggested tests."),
        ("03", "No test or medical recommendation reaches the patient without the doctor's approval."),
        ("04", "Red flags stop the call and send the patient to emergency care."),
    ],
    "foot": "The clinic, doctors and patients are fictional. Patients voiced by AI; text messages simulated.",
}
