from html import escape

from flask_mail import Message
from extensions import mail

def send_job_alert(
    recipient_email,
    student_name,
    company,
    role,
    score,
    matched_skills,
    missing_skills
):

    msg = Message(
        subject=f"AI Job Match: {role} at {company}",
        recipients=[recipient_email]
    )

    msg.html = f"""
    <h2>New Placement Opportunity</h2>

    <p>Hello {escape(str(student_name))},</p>

    <p>A new job matches your profile.</p>

    <ul>
        <li><b>Company:</b> {escape(str(company))}</li>
        <li><b>Role:</b> {escape(str(role))}</li>
        <li><b>Match Score:</b> {escape(str(score))}%</li>
    </ul>

    <h3>Matched Skills</h3>
    <p>{escape(", ".join(str(skill) for skill in matched_skills))}</p>

    <h3>Skills To Improve</h3>
    <p>{escape(", ".join(str(skill) for skill in missing_skills))}</p>

    <p>Login to PlacementLink to apply.</p>

    
    <p> Best of luck!</p>
    <p> The PlacementLink Team</p>
    """

    mail.send(msg)
