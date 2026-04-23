INSERT IGNORE INTO Students (student_id, name, email, major) VALUES
    (1001, 'Alex Kim', 'alex.kim@univ.edu', 'Computer Science'),
    (1002, 'Maya Patel', 'maya.patel@univ.edu', 'Electrical Engineering'),
    (1003, 'Noah Rivera', 'noah.rivera@univ.edu', 'Mathematics'),
    (1004, 'Olivia Chen', 'olivia.chen@univ.edu', 'Physics'),
    (1005, 'Liam Brooks', 'liam.brooks@univ.edu', 'Information Systems');

INSERT IGNORE INTO Courses (course_id, course_name, instructor) VALUES
    (447, 'Database Systems', 'Dr. Lee'),
    (448, 'Computer Networks', 'Dr. Shah'),
    (350, 'Data Structures', 'Dr. Morgan'),
    (470, 'Software Engineering', 'Dr. Alvarez'),
    (510, 'Machine Learning', 'Dr. Turner');

INSERT IGNORE INTO StudyGroups (group_id, course_id, host_student_id, meeting_time, location, notes) VALUES
    (1, 447, 1001, '2026-04-15 18:00:00', 'JRP 2045', 'Normalization and SQL practice'),
    (2, 448, 1002, '2026-04-16 17:30:00', 'Eaton 1012', 'Routing and subnetting review'),
    (3, 350, 1003, '2026-04-17 19:00:00', 'Wescoe 3050', 'Trees and graph problems'),
    (4, 470, 1004, '2026-04-18 16:00:00', 'Virtual - Zoom', 'Agile sprint planning prep');

INSERT IGNORE INTO GroupMembers (group_id, student_id) VALUES
    (1, 1001),
    (1, 1003),
    (1, 1005),
    (2, 1002),
    (2, 1004),
    (3, 1003),
    (3, 1001),
    (4, 1004),
    (4, 1002);
