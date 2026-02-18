// Feedback Detail JavaScript

// Global variables for assignee search
let selectedAssignee = { ldap: '', name: '' };
let searchTimeout;

// Comment Management
function addComment() {
    document.getElementById('commentForm').style.display = 'block';
    document.getElementById('commentText').focus();
}

function cancelComment() {
    document.getElementById('commentForm').style.display = 'none';
    document.getElementById('commentText').value = '';
    document.getElementById('isInternal').checked = false;
}

async function submitComment() {
    const commentText = document.getElementById('commentText').value.trim();
    const isInternal = document.getElementById('isInternal').checked;

    if (!commentText) {
        alert('Please enter a comment');
        return;
    }

    try {
        const response = await fetch(`/projects/feedback/${issueId}/comment/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                comment_text: commentText,
                is_internal: isInternal
            })
        });

        const data = await response.json();

        if (data.success) {
            location.reload();
        } else {
            alert('Error: ' + (data.error || 'Failed to add comment'));
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Failed to add comment');
    }
}

// Status Management
async function changeStatus() {
    const statuses = ['NEW', 'IN_PROGRESS', 'FINISHED', 'CLOSED'];
    const status = prompt('Enter new status:\n' + statuses.join('\n'));

    if (!status || !statuses.includes(status.toUpperCase())) {
        return;
    }

    await updateIssue({ status: status.toUpperCase() });
}

// Priority Management
async function changePriority() {
    const priorities = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
    const priority = prompt('Enter new priority:\n' + priorities.join('\n'));

    if (!priority || !priorities.includes(priority.toUpperCase())) {
        return;
    }

    await updateIssue({ priority: priority.toUpperCase() });
}

// LDAP Assignee Search Functionality
function initializeAssigneeSearch() {
    const searchInput = document.getElementById('assignee-search');
    const searchResults = document.getElementById('search-results');
    const clearBtn = document.getElementById('clear-assignee');
    const saveBtn = document.getElementById('save-assignee');

    if (!searchInput || !searchResults || !clearBtn || !saveBtn) {
        console.warn('Assignee search elements not found');
        return;
    }

    // Input event listener for live search
    searchInput.addEventListener('input', function() {
        const query = this.value.trim();
        clearTimeout(searchTimeout);

        if (query.length < 3) {
            searchResults.classList.remove('active');
            clearBtn.style.display = 'none';
            return;
        }

        clearBtn.style.display = 'block';
        searchTimeout = setTimeout(() => {
            searchUsers(query);
        }, 300);
    });

    // Clear button event listener
    clearBtn.addEventListener('click', function() {
        searchInput.value = '';
        selectedAssignee = { ldap: '', name: '' };
        this.style.display = 'none';
        searchResults.classList.remove('active');
        saveBtn.classList.remove('active');
    });

    // Save button event listener
    saveBtn.addEventListener('click', async function() {
        if (!selectedAssignee.ldap) {
            alert('Please select a user from the search results');
            return;
        }

        await saveAssignee();
    });

    // Click outside to close dropdown
    document.addEventListener('click', function(e) {
        if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
            searchResults.classList.remove('active');
        }
    });
}

async function searchUsers(query) {
    const searchResults = document.getElementById('search-results');

    searchResults.innerHTML = '<div class="no-results"><span class="loading-spinner"></span> Searching LDAP...</div>';
    searchResults.classList.add('active');

    try {
        const response = await fetch(`/projects/ldap-search/?q=${encodeURIComponent(query)}`);
        const data = await response.json();

        if (data.results && data.results.length > 0) {
            searchResults.innerHTML = data.results.map(user => {
                // Format: "cn <email>"
                const displayName = user.mail
                    ? `${user.cn} <${user.mail}>`
                    : user.cn;

                return `
                    <div class="search-result-item"
                         data-ldap="${user.sAMAccountName}"
                         data-name="${user.cn}">
                        <div class="result-name">${displayName}</div>
                        <div class="result-details">
                            <span><i class="fas fa-user"></i> ${user.sAMAccountName}</span>
                            ${user.title ? `<span><i class="fas fa-briefcase"></i> ${user.title}</span>` : ''}
                            ${user.mail ? `<span><i class="fas fa-envelope"></i> ${user.mail}</span>` : ''}
                        </div>
                    </div>
                `;
            }).join('');

            // Attach click handlers to result items
            document.querySelectorAll('.search-result-item').forEach(item => {
                item.addEventListener('click', function() {
                    selectUser(this.dataset.ldap, this.dataset.name);
                });
            });
        } else {
            searchResults.innerHTML = '<div class="no-results"><i class="fas fa-exclamation-circle"></i> No users found in LDAP directory</div>';
        }
    } catch (error) {
        searchResults.innerHTML = '<div class="no-results"><i class="fas fa-times-circle"></i> Error searching LDAP directory</div>';
        console.error('LDAP search error:', error);
    }
}

function selectUser(ldap, name) {
    const searchInput = document.getElementById('assignee-search');
    const searchResults = document.getElementById('search-results');
    const saveBtn = document.getElementById('save-assignee');

    selectedAssignee = { ldap, name };
    // Format as "Name <email>" as specified in requirements
    const displayValue = ldap.includes('@') ? `${name} <${ldap}>` : `${name} (${ldap})`;
    searchInput.value = displayValue;
    searchResults.classList.remove('active');
    saveBtn.classList.add('active');
}

async function saveAssignee() {
    if (!selectedAssignee.ldap) {
        alert('Please select a user from the search results');
        return;
    }

    try {
        const response = await fetch(`/projects/feedback/${issueId}/assign/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                assignee_ldap: selectedAssignee.ldap,
                assignee_name: selectedAssignee.name
            })
        });

        const data = await response.json();

        if (data.ok) {
            alert('Assignee updated successfully!');
            location.reload();
        } else {
            alert('Error: ' + (data.error || 'Failed to assign user'));
        }
    } catch (error) {
        alert('Network error occurred');
        console.error('Assign error:', error);
    }
}

// Legacy assignIssue function (deprecated - replaced by LDAP search)
async function assignIssue() {
    alert('Please use the LDAP search box in the Assignee section to assign this issue.');
}

// Generic Issue Update
async function updateIssue(updates) {
    try {
        const response = await fetch(`/projects/feedback/${issueId}/update/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(updates)
        });

        const data = await response.json();

        if (data.success) {
            location.reload();
        } else {
            alert('Error: ' + (data.error || 'Failed to update issue'));
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Failed to update issue');
    }
}

// Navigation
function editIssue() {
    window.location.href = `/projects/feedback/${issueId}/edit/`;
}

function deleteIssue() {
    if (!confirm('Are you sure you want to delete this issue? This action cannot be undone.')) {
        return;
    }

    fetch(`/projects/feedback/${issueId}/delete/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken
        }
    }).then(response => response.json())
      .then(data => {
          if (data.success) {
              window.location.href = '/projects/feedback/';
          } else {
              alert('Error: ' + (data.error || 'Failed to delete issue'));
          }
      })
      .catch(error => {
          console.error('Delete error:', error);
          alert('Failed to delete issue');
      });
}

// Attachment Management
function uploadAttachment() {
    console.log('uploadAttachment called, issueId:', issueId);
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;

    input.onchange = async (e) => {
        const files = e.target.files;
        console.log('Files selected:', files.length);
        
        if (!files || files.length === 0) {
            alert('Please select at least one file to upload');
            return;
        }
        
        const formData = new FormData();

        for (let file of files) {
            console.log('Adding file:', file.name, 'size:', file.size);
            formData.append('files', file);
        }

        try {
            console.log('Sending upload request to:', `/tasks/${issueId}/upload-attachment/`);
            const response = await fetch(`/tasks/${issueId}/upload-attachment/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken
                },
                body: formData
            });

            console.log('Response status:', response.status);
            const data = await response.json();
            console.log('Response data:', data);

            if (data.success) {
                alert(data.message || 'Files uploaded successfully!');
                location.reload();
            } else {
                alert('Error: ' + (data.error || 'Failed to upload files'));
            }
        } catch (error) {
            console.error('Upload error:', error);
            alert('Failed to upload files. Please try again.');
        }
    };

    input.click();
}

function downloadFile(path) {
    window.open(path, '_blank');
}

// Modal Management (if using modals)
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
    }
}

function submitStatusChange() {
    const newStatus = document.getElementById('statusSelect').value;
    if (newStatus) {
        updateIssue({ status: newStatus }).then(() => {
            closeModal('statusModal');
        });
    }
}

function submitPriorityChange() {
    const newPriority = document.getElementById('prioritySelect').value;
    const newSeverity = document.getElementById('severitySelect').value;

    const updates = {};
    if (newPriority) updates.priority = newPriority;
    if (newSeverity) updates.severity = newSeverity;

    if (Object.keys(updates).length > 0) {
        updateIssue(updates).then(() => {
            closeModal('priorityModal');
        });
    }
}

function submitAttachment() {
    const fileInput = document.getElementById('attachmentFile');
    if (fileInput && fileInput.files.length > 0) {
        const formData = new FormData();
        for (let file of fileInput.files) {
            formData.append('files', file);
        }

        fetch(`/tasks/${issueId}/upload-attachment/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken
            },
            body: formData
        }).then(response => response.json())
          .then(data => {
              if (data.success) {
                  alert(data.message || 'Files uploaded successfully!');
                  closeModal('uploadModal');
                  location.reload();
              } else {
                  alert('Error: ' + (data.error || 'Failed to upload'));
              }
          })
          .catch(error => {
              console.error('Upload error:', error);
              alert('Failed to upload files. Please try again.');
          });
    } else {
        alert('Please select at least one file to upload');
    }
}

function confirmDelete() {
    deleteIssue();
    closeModal('deleteModal');
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', function() {
    initializeAssigneeSearch();
});