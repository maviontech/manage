/**
 * Workflows and Priorities Pages - Interactive Features
 */

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeAnimations();
    initializeProgressCircles();
    initializeFilterButtons();
    initializeCardInteractions();
});

/**
 * Initialize card animations on scroll
 */
function initializeAnimations() {
    const cards = document.querySelectorAll('.stat-card, .priority-card, .workflow-item, .task-item');
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry, index) => {
            if (entry.isIntersecting) {
                setTimeout(() => {
                    entry.target.style.opacity = '1';
                    entry.target.style.transform = 'translateY(0)';
                }, index * 50);
            }
        });
    }, {
        threshold: 0.1
    });

    cards.forEach(card => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
        observer.observe(card);
    });
}

/**
 * Initialize animated progress circles
 */
function initializeProgressCircles() {
    const progressBars = document.querySelectorAll('.progress-fill');
    
    progressBars.forEach(bar => {
        const width = bar.style.width;
        bar.style.width = '0%';
        
        setTimeout(() => {
            bar.style.width = width;
        }, 300);
    });

    // SVG circle progress (if exists)
    const svgCircles = document.querySelectorAll('.progress-circle-fill');
    svgCircles.forEach(circle => {
        const circumference = 2 * Math.PI * circle.r.baseVal.value;
        const percent = parseFloat(circle.dataset.percent || 0);
        const offset = circumference - (percent / 100) * circumference;
        
        circle.style.strokeDasharray = circumference;
        circle.style.strokeDashoffset = circumference;
        
        setTimeout(() => {
            circle.style.strokeDashoffset = offset;
        }, 300);
    });
}

/**
 * Initialize filter button functionality
 */
function initializeFilterButtons() {
    const filterButtons = document.querySelectorAll('.filter-btn');
    const items = document.querySelectorAll('.task-item, .workflow-item');

    filterButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            // Update active state
            filterButtons.forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            const filter = this.textContent.toLowerCase().trim();

            // Apply filter with animation
            items.forEach((item, index) => {
                const shouldShow = filter === 'all' || 
                    item.classList.contains(filter) ||
                    item.querySelector(`.${filter}`);

                if (shouldShow) {
                    setTimeout(() => {
                        item.style.display = 'flex';
                        setTimeout(() => {
                            item.style.opacity = '1';
                            item.style.transform = 'translateX(0)';
                        }, 10);
                    }, index * 30);
                } else {
                    item.style.opacity = '0';
                    item.style.transform = 'translateX(-20px)';
                    setTimeout(() => {
                        item.style.display = 'none';
                    }, 300);
                }
            });
        });
    });
}

/**
 * Initialize card click interactions
 */
function initializeCardInteractions() {
    // Workflow items
    const workflowItems = document.querySelectorAll('.workflow-item');
    workflowItems.forEach(item => {
        item.addEventListener('click', function(e) {
            if (!e.target.closest('.btn-primary')) {
                const workflowId = this.dataset.workflowId;
                console.log('Workflow clicked:', workflowId);
                // Add navigation or modal logic here
                showWorkflowDetails(workflowId);
            }
        });
    });

    // Task items
    const taskItems = document.querySelectorAll('.task-item');
    taskItems.forEach(item => {
        item.addEventListener('click', function() {
            const taskId = this.dataset.taskId;
            if (taskId) {
                window.location.href = `/tasks/${taskId}/`;
            }
        });
    });

    // Priority cards
    const priorityCards = document.querySelectorAll('.priority-card');
    priorityCards.forEach(card => {
        card.addEventListener('click', function() {
            const priority = this.classList[1]; // Get priority class
            console.log('Priority card clicked:', priority);
            // Filter tasks by priority
            filterTasksByPriority(priority);
        });
    });
}

/**
 * Show workflow details (placeholder)
 */
function showWorkflowDetails(workflowId) {
    // This would typically open a modal or navigate to detail page
    console.log('Show details for workflow:', workflowId);
    // Example: window.location.href = `/workflows/${workflowId}/`;
}

/**
 * Filter tasks by priority
 */
function filterTasksByPriority(priority) {
    const taskItems = document.querySelectorAll('.task-item');
    const filterButtons = document.querySelectorAll('.filter-btn');

    // Update filter button
    filterButtons.forEach(btn => {
        if (btn.textContent.toLowerCase() === priority) {
            btn.click();
        }
    });

    // Scroll to tasks section
    const tasksSection = document.querySelector('.tasks-section');
    if (tasksSection) {
        tasksSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

/**
 * Create animated progress circle (SVG)
 */
function createProgressCircle(container, percent, size = 80) {
    const radius = (size - 8) / 2;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (percent / 100) * circumference;

    const svg = `
        <svg class="progress-circle" width="${size}" height="${size}">
            <defs>
                <linearGradient id="gradient-${Date.now()}" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" style="stop-color:#667eea;stop-opacity:1" />
                    <stop offset="100%" style="stop-color:#764ba2;stop-opacity:1" />
                </linearGradient>
            </defs>
            <circle class="progress-circle-bg" cx="${size/2}" cy="${size/2}" r="${radius}" />
            <circle class="progress-circle-fill" cx="${size/2}" cy="${size/2}" r="${radius}" 
                    style="stroke-dasharray: ${circumference}; stroke-dashoffset: ${offset};"
                    data-percent="${percent}" />
        </svg>
        <div class="progress-circle-text">${percent}%</div>
    `;

    container.innerHTML = svg;
}

/**
 * Add ripple effect to buttons
 */
function addRippleEffect(element, event) {
    const ripple = document.createElement('span');
    const rect = element.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    const x = event.clientX - rect.left - size / 2;
    const y = event.clientY - rect.top - size / 2;

    ripple.style.width = ripple.style.height = size + 'px';
    ripple.style.left = x + 'px';
    ripple.style.top = y + 'px';
    ripple.classList.add('ripple-effect');

    element.appendChild(ripple);

    setTimeout(() => {
        ripple.remove();
    }, 600);
}

// Add ripple effect to all buttons
document.querySelectorAll('.btn-primary, .filter-btn').forEach(btn => {
    btn.addEventListener('click', function(e) {
        addRippleEffect(this, e);
    });
});

/**
 * Utility: Format date
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    const options = { month: 'short', day: 'numeric', year: 'numeric' };
    return date.toLocaleDateString('en-US', options);
}

/**
 * Utility: Get priority color
 */
function getPriorityColor(priority) {
    const colors = {
        'critical': '#ef4444',
        'high': '#f59e0b',
        'normal': '#3b82f6',
        'low': '#10b981'
    };
    return colors[priority.toLowerCase()] || colors.normal;
}

/**
 * Export functions for external use
 */
window.WorkflowsPriorities = {
    createProgressCircle,
    filterTasksByPriority,
    formatDate,
    getPriorityColor
};
