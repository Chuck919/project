DROP TABLE IF EXISTS GroupMembers;
DROP TABLE IF EXISTS StudyGroups;
DROP TABLE IF EXISTS Courses;
DROP TABLE IF EXISTS Students;

CREATE TABLE Students (
    student_id INT PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    major VARCHAR(80) NOT NULL
);

CREATE TABLE Courses (
    course_id INT PRIMARY KEY,
    course_name VARCHAR(120) NOT NULL,
    instructor VARCHAR(80) NOT NULL
);

CREATE TABLE StudyGroups (
    group_id INT AUTO_INCREMENT PRIMARY KEY,
    course_id INT NOT NULL,
    host_student_id INT NOT NULL,
    meeting_time DATETIME NOT NULL,
    location VARCHAR(120) NOT NULL,
    notes VARCHAR(255) NOT NULL DEFAULT '',
    CONSTRAINT fk_studygroups_course
        FOREIGN KEY (course_id) REFERENCES Courses(course_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_studygroups_host
        FOREIGN KEY (host_student_id) REFERENCES Students(student_id)
        ON DELETE CASCADE
);

CREATE TABLE GroupMembers (
    group_id INT NOT NULL,
    student_id INT NOT NULL,
    joined_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (group_id, student_id),
    CONSTRAINT fk_groupmembers_group
        FOREIGN KEY (group_id) REFERENCES StudyGroups(group_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_groupmembers_student
        FOREIGN KEY (student_id) REFERENCES Students(student_id)
        ON DELETE CASCADE
);
