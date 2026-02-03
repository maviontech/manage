# Task Attachments Feature Implementation

## Overview
This document describes the implementation of file attachment functionality for tasks. Users can now attach files/images when creating tasks, and these attachments are displayed in the task view page within the description section.

## Changes Made

### 1. Database Schema
Created a new table `task_attachments` to store attachment metadata:

```sql
CREATE TABLE task_attachments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    task_id INT NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    file_size INT,
    file_type VARCHAR(100),
    uploaded_by INT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_task_id (task_id),
    INDEX idx_uploaded_at (uploaded_at),
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by) REFERENCES members(id) ON DELETE SET NULL
)
```

### 2. Backend Changes

#### File: `core/views_tasks.py`

**Imports Added:**
```python
import os
from django.conf import settings
from django.core.files.storage import default_storage
```

**create_task_view Function:**
- Added file upload handling after task creation
- Files are saved to `media/task_attachments/` directory
- Each file is renamed with task_id and timestamp to avoid conflicts
- File metadata is stored in the `task_attachments` table

**task_page_view Function:**
- Fetches attachments from database for the specific task
- Converts file sizes to human-readable format (B, KB, MB)
- Determines appropriate file icon based on MIME type
- Passes attachment data to template

### 3. Frontend Changes

#### File: `core/templates/core/task_page_view.html`

**Attachments Display:**
- Attachments are now displayed within the Description card
- Shows below the task description with a clear section divider
- Each attachment displays:
  - File icon (based on file type)
  - File name (clickable to view/download)
  - File size in human-readable format
  - Uploader name and upload date
  - Download button

**Image Handling:**
- Images are displayed inline with preview
- Click to open full size in new tab
- Maximum preview size: 300px height

**Non-Image Files:**
- Clickable download link with file icon
- Download button for direct download

**Styling:**
- Modern gradient backgrounds
- Hover effects for better UX
- Responsive design
- Color-coded file type icons

### 4. Scripts

#### File: `scripts/add_task_attachments_table.py`
- Database migration script to add the `task_attachments` table
- Connects to master database to get all tenant databases
- Creates the table in each tenant database
- Provides detailed progress reporting

## File Structure

```
media/
└── task_attachments/
    └── {task_id}_{timestamp}_{original_filename}
```

Files are stored with the pattern:
- `{task_id}`: The ID of the task
- `{timestamp}`: Upload timestamp in format YYYYMMDD_HHMMSS
- `{original_filename}`: The original name of the uploaded file

## Supported File Types

The attachment system supports:
- **Images**: PNG, JPG, JPEG, GIF, BMP, SVG
- **Documents**: PDF, DOC, DOCX, TXT, LOG
- **Spreadsheets**: XLS, XLSX
- **Maximum file size**: 10MB per file
- **Maximum files**: 5 files per task creation

## Usage Instructions

### For Users

1. **Creating a Task with Attachments:**
   - Navigate to Create Task page
   - Fill in task details
   - Scroll to the Attachments section
   - Click or drag & drop files to upload
   - Submit the form

2. **Viewing Attachments:**
   - Open any task detail page
   - Scroll to the Description section
   - Attachments appear below the description
   - Click file name to view/open
   - Click download button to download

3. **Image Previews:**
   - Images are automatically displayed inline
   - Click on image to view full size in new tab

### For Administrators

1. **Run Database Migration:**
   ```bash
   cd scripts
   python add_task_attachments_table.py
   ```

2. **Verify Media Directory:**
   - Ensure `media/task_attachments/` directory exists
   - Check write permissions

3. **Configure Media Serving:**
   - Ensure Django settings has correct MEDIA_URL and MEDIA_ROOT
   - Configure web server to serve media files in production

## File Type Icons

The system automatically assigns icons based on file MIME type:
- 📷 `fa-file-image`: Images
- 📄 `fa-file-pdf`: PDF documents
- 📝 `fa-file-word`: Word documents
- 📊 `fa-file-excel`: Excel spreadsheets
- 📋 `fa-file-alt`: Text files
- 📎 `fa-file`: Other file types

## Security Considerations

1. **File Size Limits**: Client-side validation limits files to 10MB
2. **File Type Restrictions**: Only specific file types are accepted
3. **File Name Sanitization**: Files are renamed to prevent path traversal attacks
4. **Database Constraints**: Foreign key constraints ensure data integrity
5. **Access Control**: Only authenticated users can upload/view attachments

## Future Enhancements

Potential improvements for future versions:
1. Delete attachment functionality
2. Add attachments after task creation
3. Bulk download all attachments
4. Attachment versioning
5. Virus scanning for uploaded files
6. Cloud storage integration (S3, Azure Blob, etc.)
7. Thumbnail generation for images
8. Preview for PDF files

## Troubleshooting

### Attachments not uploading:
- Check form has `enctype="multipart/form-data"`
- Verify media directory has write permissions
- Check file size limits
- Review server logs for errors

### Attachments not displaying:
- Verify database migration was run
- Check MEDIA_URL in settings
- Ensure media files directory is accessible
- Check browser console for errors

### Images not showing:
- Verify MEDIA_URL is correctly configured
- Check file path in database matches actual file location
- Ensure web server is serving media files

## Testing Checklist

- [x] Create task with single attachment
- [x] Create task with multiple attachments
- [x] Create task without attachments
- [x] View task with image attachments
- [x] View task with document attachments
- [x] Download attachment files
- [x] Test file size validation
- [x] Test file type validation
- [x] Check responsive design on mobile
- [x] Verify database migration script

## Deployment Notes

1. Run the database migration script on all tenant databases
2. Ensure media directory exists and has proper permissions
3. Configure web server (nginx/apache) to serve media files
4. Set appropriate MEDIA_URL in production settings
5. Consider setting up CDN for media files in production
6. Set up backup strategy for media files

## Support

For issues or questions, contact the development team or refer to the project documentation.
