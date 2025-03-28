1. Creation of ExternalGraderDetail Model for XQueue Migration
###############################################################

Status
******

**Provisional** *2025-02-10*

Implemented by https://github.com/openedx/edx-submissions/pull/283

Context
*******

Currently, Open edX uses a separate system called XQueue to handle the grading of student submissions for certain
types of problems (like programming assignments). It implements a REST API with MySQL backend,
requiring HTTP communication between services that manages submissions. This system works, but it has some limitations:

- HTTP dependency creates unnecessary synchronous coupling
- Complex state management across services
- No native queue system (implemented through database)
- Unnecessary complexity in system architecture

Decision
********

As part of Phase 1 of the XQueue migration plan, we will create a new ExternalGraderDetail model in edx-submissions to
simplify the grading system architecture. This is the first step in a larger plan that will eventually include an event
bus implementation for handling the submissions workflow.

What's New

A new database model that will:

    - Keep track of submission status more clearly
    - Store all grading-related information in one place
    - Make it easier to process submissions in order
    - Handle errors and retries automatically

Key Features

    - Better tracking of submission status (pending, being graded, completed, failed)
    - Clearer connection between submissions and their grading results
    - Improved error handling and retry capabilities
    - Easier monitoring of the grading process
    - Simplify the xqueue-watcher and edx-platform queue processing architecture
    - Reduce inter-service communication overhead

Implementation Approach

We'll implement this change gradually:

    - First, build the new system alongside the existing one
    - Test thoroughly to ensure everything works as expected
    - Slowly transition from the old system to the new one
    - Keep the old system running until we're sure the new one works perfectly

Consequences
************

Positive:
---------

Model Structure:
   * Clean data separation via OneToOneField relationship
   * Explicit state management with VALID_TRANSITIONS
   * Protected state changes using atomic transactions

Integration:
   * Compatible with existing xqueue-watcher interface
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
   * Integration testing with xqueue-watcher

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
   * ADR to follow steps migration: https://github.com/openedx/edx-platform/pull/36258

Related Repositories:
   * edx-submissions: https://github.com/openedx/edx-submissions
   * edx-platform: https://github.com/openedx/edx-platform

Future Event Integration:
   * Open edX Events Framework: https://github.com/openedx/openedx-events
   * Event Bus Documentation: https://openedx.atlassian.net/wiki/spaces/AC/pages/124125264/Event+Bus

Related Architecture Documents:
   * Open edX Architecture Guidelines: https://openedx.atlassian.net/wiki/spaces/AC/pages/124125264/Architecture+Guidelines
