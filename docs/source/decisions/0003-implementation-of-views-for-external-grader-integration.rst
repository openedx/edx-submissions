3. Implementation of XQueue Compatible Views for External Grader Integration
############################################################################

Status
******

**Provisional** *2025-02-21*

Implemented by https://github.com/openedx/edx-submissions/pull/284

Context
*******

Following the creation of ExternalGraderDetail (ADR 1) and SubmissionFile (ADR 2) models, we need to implement the API
endpoints that will allow external graders (xqueue-watcher) to interact with the system. The current XQueue implementation
provides three critical endpoints that need to be replicated:

1. Authentication Service:
   - Secure login mechanism for external graders
   - Session management
   - CSRF handling for specific endpoints

2. Submission Retrieval (get_submission):
   - Queue-based submission distribution
   - Status tracking and locking mechanism
   - File information packaging for graders

3. Result Processing (put_result):
   - Score validation and processing
   - Status updates
   - Error handling and retry mechanisms

The current XQueue implementation has these services spread across multiple systems, requiring complex HTTP communication
and session management. The existing workflow:

1. Authentication Flow:
   - Basic username/password authentication
   - Session-based token management
   - Manual CSRF handling for specific endpoints

2. Submission Processing:
   - Manual queue status checks
   - Complex state transitions
   - Synchronous HTTP-based file retrieval

3. Result Handling:
   - Direct database updates
   - Limited error recovery
   - Complex retry logic

Decision
********

We will implement a unified service approach that brings together all the functionality needed for external grader integration. This approach will:

1. Simplify Authentication:
   - Create a more straightforward login process for external graders
   - Make session handling more reliable
   - Ensure security while reducing technical complexity

2. Improve Submission Handling:
   - Create a more efficient way to distribute submissions to graders
   - Track the status of submissions more reliably
   - Provide all necessary information to graders in a consistent format

3. Enhance Results Processing:
   - Process scores more reliably
   - Handle errors gracefully
   - Provide better feedback to both graders and the platform

The solution will be built as a consolidated service that external graders can interact with through standard REST API endpoints. This will make integration easier for external services while providing better monitoring and control for the platform.

Key Benefits:

1. External graders will have a single, consistent interface
2. The platform will have better visibility into the grading process
3. Error handling will be improved across the entire workflow
4. Security will be enhanced through better authentication practices

This approach connects directly with the previously created data models for external graders and submission files, providing a complete end-to-end solution for the grading workflow.

Administrative Interface Implementation
***************************************

The ExternalGraderDetailAdmin provides comprehensive monitoring and management capabilities:

Status Management
-----------------

- Visual status badges with color coding (pending/yellow, pulled/blue, failed/red, retired/gray)
- Bulk action to reset failed submissions to pending status
- Status transition validation (only failed → pending allowed)
- Read-only fields for data integrity

Search and Filtering
--------------------

- Advanced search across queue names, pullkeys, grader files, and submission details
- Filtered search including student_id, course_id, and item_id from related submissions
- Optimized queryset with select_related for performance
- List filters by status, queue_name, failures, and timestamps

Information Display
-------------------

- Comprehensive submission information formatting (student, course, item details)
- Failure count tracking for retry logic monitoring
- Timestamp tracking for status changes and creation
- Direct links to related submission records

Security and Permissions
------------------------

- Read-only access for individual records (prevents accidental data modification)
- Superuser-only deletion permissions
- Change permissions enabled for bulk actions and viewing

Operational Features
--------------------

- Error handling with user feedback messages for bulk operations
- Database query optimization through select_related
- Fieldset organization for logical information grouping
- Integration with Django's admin messaging system

Consequences
************

Positive:
---------

1. Architecture:
   - Consolidated service endpoints
   - Clean separation of concerns
   - Improved error handling
   - Better session management

2. Security:
   - Robust authentication
   - Secure file handling
   - Protected state transitions

3. Operations:
   - Simplified deployment
   - Better monitoring capabilities
   - Improved error visibility
   - Automatic retry handling

4. Administrative Interface:
   - Comprehensive monitoring dashboard for external grader operations
   - Bulk recovery operations for failed submissions
   - Enhanced visibility into grading pipeline status
   - Optimized database queries for large-scale operations
   - User-friendly status indicators and search capabilities

Negative:
---------

1. Complexity:
   - More complex session management
   - Additional state validation required
   - Complex transaction handling

2. Performance:
   - Additional database operations
   - Session verification overhead

3. Migration:
   - Changes required in external graders
   - New deployment procedures needed

References
**********

Implementation References:

* XQueue ViewSet Implementation: Link to PR
* External Grader Integration Guide: Link to documentation

Related ADRs:

* ADR 1: Creation of ExternalGraderDetail Model
* ADR 2: File Handling Implementation

Documentation:

* XQueue API Specification
* External Grader Integration Guide
* Session Management Documentation

Architecture Guidelines:

* Django REST Framework Best Practices
* Open edX API Guidelines