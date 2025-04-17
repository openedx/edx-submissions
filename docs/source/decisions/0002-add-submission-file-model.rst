2. File Handling Implementation for Submission System
#####################################################

Status
******

**Provisional** *2025-02-14*

Implemented by https://github.com/openedx/edx-submissions/pull/286

Context
*******

As part of the XQueue migration effort detailed in ADR 0001, we need to implement a file handling system within edx-submissions. Currently, XQueue manages file submissions through a tightly coupled approach.

### Current Limitations

1. **Inadequate File Management**: XQueue's approach relies on JSON strings in character fields, with size constraints and manual URL manipulation for file handling.

2. **Process Inefficiencies**: The current system uses synchronous HTTP for file retrieval, lacks proper validation, and tightly couples submission processing with file handling.

3. **Integration Challenges**: External graders depend on specific URL formats with HTTP-based retrieval, embedding file information directly in submission payloads.

Decision
********

We will implement a dedicated file management system for the assessment submission process, focusing on workflow and educational needs:

1. **Centralized Storage**: Create a unified repository for student-submitted files, ensuring they are properly associated with their assessments and accessible throughout the grading process.

2. **Streamlined Workflow**: Design a clear process where files are automatically processed during submission creation, securely stored, and efficiently delivered to grading systems.

3. **Consistent Experience**: Maintain compatibility with existing systems to ensure a smooth transition, allowing instructors and external graders to access files without changes to their established workflows.

Consequences
************

Positive:
---------

1. **Architecture**: Clean separation of concerns, improved maintainability, better error handling, optimized database access

2. **Integration**: Seamless xqueue-watcher compatibility, support for existing workflows, minimal client code changes

3. **Operations**: Robust file validation, improved tracking, better error visibility, simplified lifecycle management

Negative:
---------

1. **Technical**: Additional database structures

2. **Migration**: Temporary system complexity, additional testing needs

3. **Performance**: File processing overhead

References
**********

Current System Documentation:
   * XQueue Repository: https://github.com/openedx/xqueue
   * XQueue Watcher Repository: https://github.com/openedx/xqueue-watcher

Related Repositories:
   * edx-submissions: https://github.com/openedx/edx-submissions
   * edx-platform: https://github.com/openedx/edx-platform
   * XQueue Repository: https://github.com/openedx/xqueue

Related Documentation:
   * ADR 0001: Creation of ExternalGraderDetail Model for XQueue Migration

Future Event Integration:
   * Open edX Events Framework: https://github.com/openedx/openedx-events
   * Event Bus Documentation: https://openedx.atlassian.net/wiki/spaces/AC/pages/124125264/Event+Bus

Related Architecture Documents:
   * Open edX Architecture Guidelines: https://openedx.atlassian.net/wiki/spaces/AC/pages/124125264/Architecture+Guidelines

