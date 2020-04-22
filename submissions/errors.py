""" Submission-specific errors """

import copy


class SubmissionError(Exception):
    """
    An error that occurs during submission actions.

    This error is raised when the submission API cannot perform a requested
    action.
    """


class SubmissionInternalError(SubmissionError):
    """
    An error internal to the Submission API has occurred.

    This error is raised when an error occurs that is not caused by incorrect
    use of the API, but rather internal implementation of the underlying
    services.
    """


class SubmissionNotFoundError(SubmissionError):
    """
    This error is raised when no submission is found for the request.

    If a state is specified in a call to the API that results in no matching
    Submissions, this error may be raised.
    """


class SubmissionRequestError(SubmissionError):
    """
    This error is raised when there was a request-specific error

    This error is reserved for problems specific to the use of the API.
    """
    def __init__(self, msg="", field_errors=None):
        """
        Configure the submission request error.

        Keyword Args:
            msg (unicode): The error message.
            field_errors (dict): A dictionary of errors (list of unicode)
                specific to a fields provided in the request.

        Example usage:

        >>> raise SubmissionRequestError(
        >>>     "An unexpected error occurred"
        >>>     {"answer": ["Maximum answer length exceeded."]}
        >>> )

        """
        super(SubmissionRequestError, self).__init__(msg)
        self.field_errors = (
            copy.deepcopy(field_errors)
            if field_errors is not None
            else {}
        )
        self.args += (self.field_errors,)

    def __repr__(self):
        """
        Show the field errors upon output.
        """
        return '{}(msg="{}", field_errors={})'.format(
            self.__class__.__name__, self.message, self.field_errors  # pylint: disable=no-member
        )


class DuplicateTeamSubmissionsError(Exception):
    """ An error that is raised when duplicate team submissions are detected. """


class TeamSubmissionNotFoundError(SubmissionNotFoundError):
    """ SubmissionNotFoundError for TeamSubmissionModels """


class TeamSubmissionInternalError(SubmissionInternalError):
    """ SubmissioonINternalError for teams """


class TeamSubmissionRequestError(SubmissionRequestError):
    """ SubmissionRequestError for teams """
