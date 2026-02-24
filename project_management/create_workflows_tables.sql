-- SQL script to create workflows table
-- Run this on your tenant database

CREATE TABLE IF NOT EXISTS workflows (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status ENUM('Active', 'Draft', 'Archived') DEFAULT 'Draft',
    created_by INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Sample data (optional)
INSERT INTO workflows (name, description, status) VALUES
('Development Workflow', 'Standard development process from planning to deployment', 'Active'),
('Bug Fix Workflow', 'Quick workflow for addressing and resolving bugs', 'Active'),
('Feature Request Workflow', 'Process for evaluating and implementing new features', 'Draft'),
('Code Review Workflow', 'Peer review process for code quality assurance', 'Active'),
('Release Workflow', 'Steps for preparing and deploying releases', 'Draft');
