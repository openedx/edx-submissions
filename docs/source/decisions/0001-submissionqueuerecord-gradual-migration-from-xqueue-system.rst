1. Creation of ExternalGraderDetail Model for XQueue Migration
###############################################################

Status
******

**Provisional** *2025-02-10*

Implemented by https://github.com/openedx/edx-submissions/pull/283

Context
*******

The current XQueue system operates as a separate service from edx-submissions, implementing a REST API with MySQL
backend, requiring HTTP communication between services that manages submissions through these key endpoints:

1. LMS Integration (/submit/):

   - Handles incoming submissions from LMS
   - Manages file uploads and queue assignments
   - Creates Submission records with unique identifiers

2. External Grader Interface:

   - /get_submission/: Provides submissions to graders
   - /put_result/: Processes grading results
   - /get_queuelen/: Monitors queue status

Current Database Structure (Submission Model):

- Core submission data (requester_id, queue_name, headers, body)
- File handling (s3_keys, s3_urls for uploads)
- State tracking fields (arrival_time, pull_time, push_time, return_time)
- Processing metadata (grader_id, pullkey, num_failures)
- Status flags (lms_ack, retired)

Communication Flow:

1. LMS → XQueue:

   - Authenticated POST requests with submission data
   - File upload handling through Django storage
   - Queue validation and assignment

2. XQueue → XWatcher:

   - Pull-based retrieval of submissions
   - State tracking through timestamps
   - File URL management for external access

3. XWatcher → XQueue:

   - Result submission with validation
   - Automatic retirement after failed attempts
   - LMS callback handling

This architecture has limitations:

- HTTP dependency creates unnecessary synchronous coupling
- Complex state management across services
- No native queue system (implemented through database)
- Unnecessary complexity in system architecture

Decision
********

As part of Phase 1 of the XQueue migration plan, we will create a new ExternalGraderDetail model in edx-submissions as follows:

Model Structure and Technical Details
-------------------------------------

1. Core Fields and Types:

   * submission: OneToOneField to Submission model, ensuring 1:1 relationship and data integrity
   * queue_name: CharField(128), identifies the processing submission queue to segment a problem batch for xwatcher
   * status: CharField(20) with choices ['pending', 'pulled', 'retired', 'failed'] to track submission lifecycle
   * pullkey: CharField(128), for xwatcher response validation
   * grader_reply: TextField, stores grading response
   * grader_file_name: CharField(128), Identify the external grader that xwatcher should use
   * points_possible: PositiveIntegerField, maximum score
   * status_time: DateTimeField, tracks state changes
   * created_at: DateTimeField, submission creation time
   * num_failures: PositiveIntegerField, tracks processing attempts

2. State Management:

   Valid state transitions defined as:

   * pending → [pulled, failed]
   * pulled → [retired, failed]
   * failed → [pending]
   * retired → [] (terminal state)

3. Database Optimizations:

   * Composite index on (queue_name, status, status_time) for efficient querying
   * Default ordering by created_at for consistent retrieval
   * status_time indexed for processing window queries
   * Atomic state transitions with update_fields optimization

4. Core Features Implementation:

   * Explicit state validation through can_transition_to method
   * Atomic status updates with transaction management
   * Processing window control through time_filter
   * Failure tracking and automatic retry management

Migration Strategy and Integration
----------------------------------

1. Compatibility Layer:

   * Implementation as a plug-and-play component to allow gradual adoption
   * Maintain queue_name compatibility with XQueue
   * Support existing XWatcher interface patterns
   * Enable gradual transition from legacy system

2. Initial Scope:

   * Focus on core model implementation and basic creation functionality
   * Essential queue processing methods
   * Maintain existing XQueue service while new system is validated
   * Deferral of advanced features to future PRs

This decision is part of a larger architectural change that will:

Simplify the xwatcher and edx platform queue processing architecture

Reduce inter-service communication overhead

Provide a clear path for future Xqueue functionality migration

Enable gradual system migration without disrupting existing services

Implement an event bus as second option to handle submissions workflow

Consequences
************

Positive:
---------

Model Structure:
   * Clean data separation via OneToOneField relationship
   * Explicit state management with VALID_TRANSITIONS
   * Protected state changes using atomic transactions

Integration:
   * Compatible with existing XWatcher interface
   * Maintains current queue naming patterns
   * Enables parallel system operation during migration

Development:
   * Integrated status validation and retry
   * Comprehensive status tracking

Negative:
---------

Technical Challenges:
   * Required atomic updates for status and timestamps
   * Additional database overhead from new indexes

Testing Needs:
   * Comprehensive state transition testing required
   * Integration testing with xwatcher

Neutral:
--------

Process Impact:
   * New queue processing patterns to learn
   * Additional monitoring requirements

Operations:
   * State transition monitoring needed
   * Temporary increased system complexity

References
**********

Current System Documentation:
   * XQueue Repository: https://github.com/openedx/xqueue
   * XQueue Watcher Repository: https://github.com/openedx/xqueue-watcher

Migration Documents:
   * Current XQueue Documentation: https://github.com/openedx/edx-submissions/tree/master/docs

Related Repositories:
   * edx-submissions: https://github.com/openedx/edx-submissions
   * edx-platform: https://github.com/openedx/edx-platform

Future Event Integration:
   * Open edX Events Framework: https://github.com/openedx/openedx-events
   * Event Bus Documentation: https://openedx.atlassian.net/wiki/spaces/AC/pages/124125264/Event+Bus

Related Architecture Documents:
   * Open edX Architecture Guidelines: https://openedx.atlassian.net/wiki/spaces/AC/pages/124125264/Architecture+Guidelines
