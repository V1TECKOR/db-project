-- Interclub Tennis Organizer schema

CREATE TABLE IF NOT EXISTS clubs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(120) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS license_club_map (
  id INT AUTO_INCREMENT PRIMARY KEY,
  license_prefix VARCHAR(20) NOT NULL UNIQUE,
  club_id INT NOT NULL,
  FOREIGN KEY (club_id) REFERENCES clubs(id)
);

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  first_name VARCHAR(80) NOT NULL,
  last_name VARCHAR(80) NOT NULL,
  email VARCHAR(190) NOT NULL UNIQUE,
  license_number VARCHAR(40) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  club_id INT NULL,
  role VARCHAR(20) NOT NULL DEFAULT 'player', -- player | captain | club_admin
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (club_id) REFERENCES clubs(id)
);

CREATE TABLE IF NOT EXISTS teams (
  id INT AUTO_INCREMENT PRIMARY KEY,
  club_id INT NOT NULL,
  name VARCHAR(120) NOT NULL,
  captain_id INT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (club_id) REFERENCES clubs(id),
  FOREIGN KEY (captain_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS team_membership (
  user_id INT NOT NULL,
  team_id INT NOT NULL,
  is_approved BOOLEAN NOT NULL DEFAULT FALSE,
  requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  approved_at TIMESTAMP NULL,
  PRIMARY KEY (user_id, team_id),
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (team_id) REFERENCES teams(id)
);

CREATE TABLE IF NOT EXISTS matches (
  id INT AUTO_INCREMENT PRIMARY KEY,
  team_id INT NOT NULL,
  opponent VARCHAR(140) NOT NULL,
  location VARCHAR(80) NOT NULL DEFAULT 'Home', -- Home/Away/Other
  final_date DATETIME NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'planned', -- planned|confirmed|completed
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (team_id) REFERENCES teams(id)
);

CREATE TABLE IF NOT EXISTS match_dates (
  id INT AUTO_INCREMENT PRIMARY KEY,
  match_id INT NOT NULL,
  proposed_datetime DATETIME NOT NULL,
  FOREIGN KEY (match_id) REFERENCES matches(id)
);

CREATE TABLE IF NOT EXISTS availability (
  id INT AUTO_INCREMENT PRIMARY KEY,
  match_date_id INT NOT NULL,
  user_id INT NOT NULL,
  available BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uniq_avail (match_date_id, user_id),
  FOREIGN KEY (match_date_id) REFERENCES match_dates(id),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS lineup (
  match_id INT NOT NULL,
  user_id INT NOT NULL,
  confirmed BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (match_id, user_id),
  FOREIGN KEY (match_id) REFERENCES matches(id),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS match_tasks (
  match_id INT NOT NULL,
  task VARCHAR(50) NOT NULL, -- Balls, Drinks, Transport
  user_id INT NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (match_id, task),
  FOREIGN KEY (match_id) REFERENCES matches(id),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS match_messages (
  id INT AUTO_INCREMENT PRIMARY KEY,
  match_id INT NOT NULL,
  user_id INT NOT NULL,
  content TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (match_id) REFERENCES matches(id),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Seed example club + mapping (EDIT FOR YOUR REAL CLUBS)
INSERT IGNORE INTO clubs (name) VALUES ('TC Riesbach');

-- Example: license prefix mapping.
-- If your license numbers start with something like "RIES", map that prefix.
INSERT IGNORE INTO license_club_map (license_prefix, club_id)
SELECT 'RIES', id FROM clubs WHERE name='TC Riesbach';
