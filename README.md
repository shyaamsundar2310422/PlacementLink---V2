<h1 align="center"> PlacementLink</h1>
<h3 align="center">Intelligent Placement & Career Development Management System</h3>

<p align="center">
A Flask + MySQL based web application designed to streamline, automate, and optimize the college placement process through intelligent job matching, application tracking, mentor workflows, and placement analytics.
</p>

<hr>

<h2> Features</h2>

<h3> Student</h3>
<ul>
<li>Register and log in using email or username</li>
<li>Create and maintain placement profile</li>
<li>Upload resumes and supporting documents</li>
<li>Browse and search job opportunities</li>
<li>View intelligent job match scores</li>
<li>Apply only for eligible jobs</li>
<li>Track application status in real time</li>
<li>Receive notifications and placement updates</li>
<li>Access training resources</li>
<li>Submit post-placement feedback</li>
</ul>

<h3> Mentor</h3>
<ul>
<li>View assigned students</li>
<li>Access student placement profiles</li>
<li>Review profile updates</li>
<li>Approve or reject profile modification requests</li>
<li>Monitor student placement readiness</li>
</ul>

<h3> Admin</h3>
<ul>
<li>Manage companies and recruiters</li>
<li>Create and manage job postings</li>
<li>Track applicants and application stages</li>
<li>Publish notifications and announcements</li>
<li>Manage placement resources and training materials</li>
<li>View advanced placement analytics</li>
<li>Export placement reports as CSV</li>
<li>Track application audit history</li>
</ul>

<hr>

<h2> Intelligent Job Matching Engine</h2>

<p>
PlacementLink uses a weighted job-matching engine that evaluates student-job compatibility using multiple placement factors instead of simple keyword matching.
</p>

<h3> Matching Parameters</h3>

<ul>
<li>Technical Skills</li>
<li>CGPA Eligibility</li>
<li>Backlog Count</li>
<li>Department Eligibility</li>
<li>Projects</li>
<li>Certifications</li>
<li>Role Relevance</li>
</ul>

<h3> Scoring Weights</h3>

<ul>
<li><b>Skills:</b> 35%</li>
<li><b>Academics:</b> 20%</li>
<li><b>Department Eligibility:</b> 15%</li>
<li><b>Role Relevance:</b> 15%</li>
<li><b>Projects:</b> 10%</li>
<li><b>Certifications:</b> 5%</li>
</ul>

<p>
Students receive a detailed match-score breakdown and can apply only when eligibility criteria and minimum match thresholds are satisfied.
</p>

<hr>

<h2> Placement Analytics Dashboard</h2>

<ul>
<li>Placement Percentage</li>
<li>Highest CTC</li>
<li>Average CTC</li>
<li>Total Placed Students</li>
<li>Department-wise Placement Statistics</li>
<li>Company-wise Recruitment Analysis</li>
<li>Placement Trend Charts</li>
<li>Department Performance Reports</li>
<li>Company Selection Ratios</li>
<li>Recent Placement Activity</li>
<li>Application Status Audit History</li>
<li>CSV Report Export</li>
</ul>

<hr>

<h2> System Architecture</h2>

<p>
<b>Frontend:</b> HTML5, CSS3, JavaScript, Bootstrap<br>
<b>Backend:</b> Python (Flask Framework)<br>
<b>Database:</b> MySQL
</p>

<h3> Layers</h3>

<ul>
<li><b>Presentation Layer</b> – User interfaces and dashboards</li>
<li><b>Application Layer</b> – Business logic and workflow management</li>
<li><b>Data Layer</b> – Database operations and persistence</li>
<li><b>Analytics Layer</b> – Placement insights and reporting</li>
</ul>

<hr>

<h2> Backend Structure (Flask Blueprints)</h2>

<ul>
<li><b>auth_routes.py</b> – Authentication and access control</li>
<li><b>student_routes.py</b> – Student functionalities</li>
<li><b>mentor_routes.py</b> – Mentor operations</li>
<li><b>admin_routes.py</b> – Administrative operations</li>
</ul>

<hr>

<h2> Database Design</h2>

<ul>
<li>users – Authentication and role management</li>
<li>students – Student information</li>
<li>mentors – Mentor information</li>
<li>admins – Administrator information</li>
<li>profiles – Placement profiles</li>
<li>companies – Recruiter information</li>
<li>jobs – Job postings</li>
<li>applications – Job applications</li>
<li>application_status – Status tracking</li>
<li>audit_logs – Application status history</li>
<li>notifications – Announcements and updates</li>
<li>documents – Resume and file uploads</li>
<li>training_resources – Learning materials</li>
<li>feedback – Placement feedback</li>
</ul>

<hr>

<h2> Authentication & Authorization</h2>

<ul>
<li>Secure login using email/username and password</li>
<li>Password hashing using Werkzeug</li>
<li>Session-based authentication</li>
<li>Role-based access control (Student, Mentor, Admin)</li>
<li>Protected routes and authorization checks</li>
<li>Environment variable based configuration</li>
</ul>

<hr>

<h2> Key Functional Highlights</h2>

<ul>
<li>Role-based placement management platform</li>
<li>Weighted job recommendation engine</li>
<li>Eligibility-aware job application workflow</li>
<li>Mentor approval process</li>
<li>Real-time application tracking</li>
<li>Notification and communication system</li>
<li>Placement analytics dashboard</li>
<li>CSV report generation</li>
<li>Application audit logging</li>
<li>Centralized placement operations management</li>
</ul>

<hr>

<h2> Workflow</h2>

<ul>
<li>Student registration and profile creation</li>
<li>Profile review and mentor validation</li>
<li>Intelligent eligibility and match evaluation</li>
<li>Job browsing and application submission</li>
<li>Application review and status updates</li>
<li>Selection or rejection outcome</li>
<li>Feedback collection and placement analytics</li>
</ul>

<hr>

<h2> Installation & Setup</h2>

<pre>
# Clone repository
git clone https://github.com/shyaamsundar2310422/PlacementLink.git

# Navigate to project
cd PlacementLink

# Create virtual environment
py -3.11 -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Initialize database
python .\database\init_db.py

# Seed sample data
python .\seed_database.py

# Run application
python .\app.py
</pre>

<hr>

<h2> Database Configuration</h2>

<pre>
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = "your_password"
DB_NAME = "placement_db"
</pre>

<hr>

<h2> Access the Application</h2>

<p>
<b>http://127.0.0.1:5000/</b>
</p>

<hr>

<h2> Future Enhancements</h2>

<ul>
<li>NLP-based Resume Parsing</li>
<li>Resume-to-Job Semantic Matching using Transformers</li>
<li>Placement Readiness Prediction Models</li>
<li>REST API Support</li>
<li>Docker Containerization</li>
<li>Cloud Deployment (AWS, Azure, GCP)</li>
</ul>

<hr>

<h2> Team</h2>

<ul>
<li>Shyaam Sundar M</li>
<li>Srivignesh R</li>
<li>Sushmidha S</li>
<li>Swetha V</li>
<li>Venkata Navadeep Reddy</li>
<li>Yaazhini A</li>
</ul>

<hr>

<h2> Conclusion</h2>

<p>
PlacementLink is a centralized, scalable, and data-driven placement management platform that combines intelligent job matching, application workflow automation, mentor review processes, placement analytics, and reporting tools to improve placement efficiency and student career outcomes.
</p>
