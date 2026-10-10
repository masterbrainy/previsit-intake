"""A demo intake that is already most of the way through, so a short live demo reaches the read-back, advice and the
doctor's approval without an emergency. Every person and detail here is fictional.

The conversation has covered consent, identity and the history; the assistant is partway through the final safety
questions. A few calm answers ("No, none of that", "I'm drinking fine, no rash") finish it.
"""

from datetime import date, timedelta

from sqlmodel import Session, select

from previsit.models import Intake, IntakeState, Speaker, Turn, utcnow

NAME = "David Chen"
DOB = date(1980, 3, 14)
SEX = "M"
CONTACT = "+15555550144"
REASON = "Fever for 4 days"
DOCTOR = "Dr. Anika Rao"

A, P = Speaker.AGENT, Speaker.PATIENT
TURNS = (
    (A, "Hello, I'm the pre-visit assistant for Riverside Family Clinic (synthetic demo). Before your appointment I'd "
        "like to ask some questions about your health so your doctor is prepared. This conversation is recorded and "
        "shared with your doctor. I'm an automated assistant, not a doctor, so I can't tell you what's wrong. If at any "
        "point you feel very unwell, please call 911. Are you happy to continue?"),
    (P, "Yes, that's fine."),
    (A, "Thank you. First, please tell me the patient's full name and date of birth. If you're answering for someone "
        "else, please also tell me how you're related to them."),
    (P, "David Chen, 14 March 1980. It's me."),
    (A, "Thank you, David. What's been troubling you? Please tell me about each problem and when it started."),
    (P, "I've had a fever for four days, and a dry cough for the last two days. I'd been feeling really tired for "
        "about a week before the fever started."),
    (A, "I'm sorry you've been unwell. What's the highest temperature you've measured, and how did you measure it?"),
    (P, "39.4 on Tuesday night, with a thermometer under my tongue. It's usually worse in the evenings."),
    (A, "Thanks. Did the fever come on suddenly or gradually, and have you had chills or shivering?"),
    (P, "Gradually. I get chills in the evening when it goes up."),
    (A, "Have you taken anything for it, and did it help?"),
    (P, "Paracetamol, it brings it down for a few hours and then it comes back."),
    (A, "And the cough: is it dry, or are you bringing anything up?"),
    (P, "Dry. It's annoying at night but not too bad."),
    (A, "Thank you. Do you have any long-term health conditions, or have you been in hospital or had an operation?"),
    (P, "High blood pressure, for about five years. No operations."),
    (A, "Do you take any regular medicines or supplements?"),
    (P, "Amlodipine 5 milligrams once a day."),
    (A, "Are you allergic to any medicines or foods? If so, what happened?"),
    (P, "Penicillin. I got a rash all over when I was a kid."),
    (A, "Thank you. Do any health problems run in your family, in your parents, brothers or sisters?"),
    (P, "My dad has type 2 diabetes. My mum is healthy."),
    (A, "What do you do for work, and who do you live with?"),
    (P, "I work in an office. I live with my wife and our two kids, who both had a cold last week."),
    (A, "Do you smoke or drink alcohol, and how have your appetite and sleep been?"),
    (P, "I don't smoke. A glass of wine at the weekend. Appetite's down and I'm not sleeping well with the fever."),
    (A, "Have you travelled anywhere in the last three months?"),
    (P, "No, nowhere."),
    (A, "Thanks, nearly done. Before we finish I ask everyone about a few warning signs. Have you had any chest pain, "
        "or any trouble breathing even when you're resting?"),
)


def seed_mid_intake(session: Session, appointment_id: int) -> None:
    """Fills the appointment's intake with the conversation above, waiting for the patient's next answer."""
    intake = session.exec(select(Intake).where(Intake.appointment_id == appointment_id)).one()
    start = utcnow() - timedelta(minutes=12)
    for seq, (speaker, text) in enumerate(TURNS, start=1):
        session.add(Turn(intake_id=intake.id, seq=seq, speaker=speaker, text=text,
                         created_at=start + timedelta(seconds=20 * seq)))
    intake.state = IntakeState.INTERVIEW
    intake.module_ids = ["fever"]
    intake.started_at = start
    session.add(intake)
