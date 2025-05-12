2. File Handling Implementation for Submission System
#####################################################

Status
******

**Provisional** *2025-02-14*

Implemented by: waiting for it

Context
*******

As part of the XQueue migration effort detailed in ADR 1, we need to handle file submissions that were previously
managed by the XQueue system. The existing implementation lacks dedicated file handling capabilities within
edx-submissions, requiring:

1. File Management:
   - Secure storage of student-submitted files
   - Association with specific submissions
   - Compatibility with XQueue URL formats
   - Support for multiple file types and formats

2. Processing Requirements:
   - Robust error handling for file operations
   - Validation of file objects
   - Dynamic path generation
   - Proper cleanup and resource management

3. Integration Points:
   - Connection with SubmissionQueueRecord
   - Support for existing xqueue-watcher interface
   - File URL format compatibility
   - Efficient database querying

The current XQueue system implements file handling through its Submission model, which manages file storage and
retrieval in a tightly coupled way. The existing implementation:

1. Current File Management in XQueue:
   - Uses a Submission model with direct file storage fields (s3_keys and s3_urls)
   - Handles file uploads through manual storage management functions (upload_file_dict, upload)
   - Stores file URLs as JSON strings in model fields
   - Requires synchronous HTTP communication for file retrieval

2. Submission Model File Fields:
   ```python
   s3_keys = models.CharField(max_length=CHARFIELD_LEN_LARGE)  # keys for internal use
   s3_urls = models.CharField(max_length=CHARFIELD_LEN_LARGE)  # urls for external access
   ```

3. Current Workflow Issues:
   - File handling is tightly coupled with submission processing
   - Relies on manual URL construction and string manipulation
   - Lacks proper file validation and type checking
   - Limited by CharField size for storing file information
   - Requires complex get_submission logic for file retrieval

4. Xqueue-watcher Integration:
   - External graders rely on specific URL formats
   - File access depends on HTTP-based retrieval
   - File information is embedded in submission payload

Decision
********

We will implement a new SubmissionFile model and supporting infrastructure to handle file management within
edx-submissions:

1. Core Model Structure:
   - SubmissionFile model with UUID-based identification
   - Foreign key relationship to SubmissionQueueRecord
   - Django FileField for actual file storage
   - Original filename preservation
   - Creation timestamp tracking
   - Composite index for efficient querying

2. File Management Layer:
   - SubmissionFileManager class for encapsulated file operations
   - Robust file processing with multiple format support
   - Error handling for various file-related exceptions
   - XQueue-compatible URL generation

3. Integration with Submission Creation:
   - Extended create_external_grader_detail function
   - File processing during submission creation
   - Automatic file manager instantiation
   - Error handling and logging

Consequences
************

Positive:
---------

1. Architecture:
   - Clean separation of concerns for file handling
   - Improved maintainability through dedicated models
   - Better error handling and logging
   - Efficient database querying through proper indexing

2. Integration:
   - Seamless xqueue-watcher compatibility
   - Support for existing file processing workflows
   - Minimal changes required to client code

3. Operations:
   - More robust file processing
   - Better tracking of file submissions
   - Improved error visibility
   - Simplified file management

Negative:
---------

1. Technical Impact:
   - Additional database tables and indexes
   - Increased storage requirements
   - More complex submission creation flow

2. Migration Considerations:
   - Temporary increased system complexity
   - Additional testing requirements

3. Performance:
   - Additional database operations during submission
   - File processing overhead

References
**********

Current System Documentation:
   * XQueue Repository: https://github.com/openedx/xqueue
   * XQueue Watcher Repository: https://github.com/openedx/xqueue-watcher

Related Repositories:
   * edx-submissions: https://github.com/openedx/edx-submissions
   * edx-platform: https://github.com/openedx/edx-platform
   * XQueue Repository: https://github.com/openedx/xqueue
   * edx-submissions: https://github.com/openedx/edx-submissions

Related Documentation:
   * ADR 1: Creation of SubmissionQueueRecord Model for XQueue Migration
   * File Processing Documentation: https://github.com/openedx/edx-submissions/tree/master/docs

Future Event Integration:
   * Open edX Events Framework: https://github.com/openedx/openedx-events
   * Event Bus Documentation: https://openedx.atlassian.net/wiki/spaces/AC/pages/124125264/Event+Bus

Related Architecture Documents:
   * Open edX Architecture Guidelines: https://openedx.atlassian.net/wiki/spaces/AC/pages/124125264/Architecture+Guidelines
