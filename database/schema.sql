CREATE DATABASE IF NOT EXISTS placement_db;
USE placement_db;

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('student', 'mentor', 'admin') NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE mentors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    faculty_id VARCHAR(50) UNIQUE NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    department VARCHAR(100) NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    register_number VARCHAR(50) UNIQUE NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    department VARCHAR(100) NOT NULL,
    mentor_id INT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (mentor_id) REFERENCES mentors(id) ON DELETE SET NULL
);

CREATE TABLE admins (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    admin_id VARCHAR(50) UNIQUE NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE student_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    cgpa DECIMAL(4,2) DEFAULT 0.00,
    skills TEXT,
    projects TEXT,
    certifications TEXT,
    resume_url VARCHAR(255),
    backlog_count INT DEFAULT 0,
    contact_number VARCHAR(20),
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

CREATE TABLE profile_update_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    mentor_id INT NOT NULL,
    requested_changes TEXT NOT NULL,
    status ENUM('pending', 'approved', 'rejected') DEFAULT 'pending',
    rejection_reason TEXT,
    reviewed_at TIMESTAMP NULL,
    request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (mentor_id) REFERENCES mentors(id) ON DELETE CASCADE
);

CREATE TABLE companies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    website_url VARCHAR(255),
    profile TEXT,
    past_history TEXT
);

CREATE TABLE jobs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT NOT NULL,
    title VARCHAR(200) NOT NULL,
    role VARCHAR(200),
    location VARCHAR(150),
    ctc VARCHAR(100),
    eligibility_criteria TEXT,
    required_skills TEXT,
    allowed_departments TEXT, -- Comma-separated or JSON
    max_backlogs INT DEFAULT 0,
    min_cgpa DECIMAL(4,2) DEFAULT 0.00,
    application_deadline DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
);

CREATE TABLE applications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    job_id INT NOT NULL,
    student_id INT NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

CREATE TABLE application_status (
    id INT AUTO_INCREMENT PRIMARY KEY,
    application_id INT NOT NULL,
    stage ENUM('Applied', 'Shortlisted', 'Aptitude Test', 'Technical Interview', 'HR Interview', 'Selected', 'Rejected') DEFAULT 'Applied',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE
);

CREATE TABLE application_status_audit (
    id INT AUTO_INCREMENT PRIMARY KEY,
    application_id INT NOT NULL,
    changed_by INT,
    previous_stage VARCHAR(50),
    new_stage VARCHAR(50) NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE,
    FOREIGN KEY (changed_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    type VARCHAR(100),
    target_role ENUM('student', 'mentor', 'admin', 'all'),
    target_department VARCHAR(100) DEFAULT 'all',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    doc_type VARCHAR(100) NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

CREATE TABLE training_resources (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    resource_type VARCHAR(100),
    url VARCHAR(255) NOT NULL,
    uploaded_by INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (uploaded_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE feedback (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    company_id INT NOT NULL,
    job_id INT NOT NULL,
    interview_process_rating INT CHECK(interview_process_rating >= 1 AND interview_process_rating <= 5),
    company_experience_rating INT CHECK(company_experience_rating >= 1 AND company_experience_rating <= 5),
    difficulty_level VARCHAR(50),
    suggestions TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
