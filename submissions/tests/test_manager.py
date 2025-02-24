"""Tests for submission models."""
# Django imports
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

# Local imports
from submissions.models import ExternalGraderDetail, StudentItem, Submission, SubmissionFile, SubmissionFileManager


class TestSubmissionFileManager(TestCase):
    """
    Test the SubmissionFileManager functionality.
    """

    def setUp(self):
        """Set up common test data."""
        self.student_item = StudentItem.objects.create(
            student_id="test_student",
            course_id="test_course",
            item_id="test_item"
        )
        self.submission = Submission.objects.create(
            student_item=self.student_item,
            answer="test answer",
            attempt_number=1
        )
        self.queue_record = ExternalGraderDetail.objects.create(
            submission=self.submission,
            queue_name="test_queue"
        )
        self.manager = SubmissionFileManager(self.queue_record)

    def test_process_files_with_bytes(self):
        """Test processing files passed as bytes."""
        files_dict = {
            "test.txt": b"test content"
        }
        urls = self.manager.process_files(files_dict)
        self.assertEqual(len(urls), 1)
        self.assertTrue(urls["test.txt"].startswith(f"/{self.queue_record.queue_name}/"))

    def test_process_files_with_file_objects(self):
        """Test processing files passed as file objects."""
        file_obj = SimpleUploadedFile("test.txt", b"test content")
        files_dict = {"test.txt": file_obj}
        urls = self.manager.process_files(files_dict)
        self.assertEqual(len(urls), 1)
        self.assertTrue(urls["test.txt"].startswith(f"/{self.queue_record.queue_name}/"))

    def test_get_files_for_grader(self):
        """Test retrieving files in xwatcher format."""
        # Create some test files first
        file1 = SimpleUploadedFile("test1.txt", b"content1")
        file2 = SimpleUploadedFile("test2.txt", b"content2")

        self.manager.process_files({
            "test1.txt": file1,
            "test2.txt": file2
        })

        grader_files = self.manager.get_files_for_grader()
        self.assertEqual(len(grader_files), 2)
        self.assertTrue(all(isinstance(url, str) for url in grader_files.values()))

    def test_process_files_with_invalid_file(self):
        """Test handling of invalid file objects."""
        files_dict = {
            "test.txt": "invalid file object"
        }
        urls = self.manager.process_files(files_dict)
        self.assertEqual(len(urls), 0)

    def test_process_files_with_read_error(self):
        """Test handling of files that raise IOError when read."""

        class ErrorFile:
            def read(self):
                raise IOError("Test error")

        files_dict = {"test.txt": ErrorFile()}
        urls = self.manager.process_files(files_dict)
        self.assertEqual(len(urls), 0)

    def test_process_files_with_readable_object(self):
        """
        Test processing files with a readable object that returns bytes.
        Tests the hasattr(file_obj, 'read') branch.
        """

        class ReadableObject:
            def read(self):
                return b"test content in bytes"

        files_dict = {"test.txt": ReadableObject()}
        urls = self.manager.process_files(files_dict)
        self.assertEqual(len(urls), 1)
        self.assertTrue(urls["test.txt"].startswith(f"/{self.queue_record.queue_name}/"))

    # HEREE------------

    def test_process_files_complete_flow(self):
        """
        Test the complete flow of processing a file through to SubmissionFile creation.
        """
        test_content = b"test binary content"
        files_dict = {"complete_test.txt": ContentFile(test_content, name="complete_test.txt")}

        # Process the file
        urls = self.manager.process_files(files_dict)

        # Verify URL was created
        self.assertEqual(len(urls), 1)
        file_url = urls["complete_test.txt"]
        self.assertTrue(file_url.startswith(f"/{self.queue_record.queue_name}/"))

        # Verify SubmissionFile was created correctly
        submission_file = SubmissionFile.objects.get(
            submission_queue=self.queue_record,
            original_filename="complete_test.txt"
        )
        self.assertEqual(submission_file.xqueue_url, file_url)
        self.assertEqual(submission_file.file.read(), test_content)

    def test_process_files_with_non_bytes_content(self):
        """Test case where read() returns content that is not bytes."""

        class NonBytesFile:
            def read(self):
                return 123  # Retorna int, no bytes ni str

        files_dict = {"test.txt": NonBytesFile()}
        urls = self.manager.process_files(files_dict)
        self.assertEqual(len(urls), 0)

    def test_process_files_with_io_error(self):
        """Test case where read() raises IOError."""

        class IOErrorFile:
            def read(self):
                raise IOError("Test IO error")

        files_dict = {"test.txt": IOErrorFile()}
        urls = self.manager.process_files(files_dict)
        self.assertEqual(len(urls), 0)

    def test_process_files_with_os_error(self):
        """Test case where read() raises OSError."""

        class OSErrorFile:
            def read(self):
                raise OSError("Test OS error")

        files_dict = {"test.txt": OSErrorFile()}
        urls = self.manager.process_files(files_dict)
        self.assertEqual(len(urls), 0)

    def test_process_files_with_unicode_decode_error(self):
        """
        Test handling of files that raise UnicodeDecodeError when read.
        """

        class UnicodeErrorFile:
            def read(self):
                raise UnicodeDecodeError('utf-8', b'test', 0, 1, 'test error')

        files_dict = {"test.txt": UnicodeErrorFile()}
        urls = self.manager.process_files(files_dict)
        self.assertEqual(len(urls), 0)

    def test_process_files_with_bytes_content(self):
        """Test case where read() returns bytes - positive case."""

        class BytesFile:
            def read(self):
                return b"test content"

        files_dict = {"test.txt": BytesFile()}
        urls = self.manager.process_files(files_dict)
        self.assertEqual(len(urls), 1)
        submission_file = SubmissionFile.objects.get(
            submission_queue=self.queue_record,
            original_filename="test.txt"
        )
        self.assertEqual(submission_file.xqueue_url, urls.get("test.txt"))

    def test_process_files_without_read_method(self):
        """Test case where file object doesn't have read() method."""

        class NoReadFile:
            pass

        files_dict = {"test.txt": NoReadFile()}
        urls = self.manager.process_files(files_dict)
        self.assertEqual(len(urls), 0)
