"""Tests for the CommentFetcher class."""

import unittest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from datetime import datetime
import time

import praw
from praw.models import Comment, Submission, MoreComments
from praw.exceptions import PRAWException

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetchers.comment import CommentFetcher
from fetchers.enums import (
    CommentField,
    CommentStatField,
    CommentBodyStatus,
    DistinguishedStatus,
    RedditObjectPrefix,
    CollapsedReason
)


class TestCommentFetcher(unittest.TestCase):
    """Test cases for CommentFetcher."""

    def setUp(self):
        """Set up test fixtures."""
        self.reddit_client = Mock(spec=praw.Reddit)
        self.fetcher = CommentFetcher(
            reddit_client=self.reddit_client,
            max_retries=2,
            retry_delay=0.1,
            replace_more_limit=None,
            replace_more_threshold=10
        )

    def _create_mock_comment(self, comment_id, author_name="test_user",
                           body="Test comment", score=10, parent_id=None,
                           depth=0, is_deleted=False, is_removed=False,
                           distinguished=DistinguishedStatus.NONE,
                           collapsed_reason=CollapsedReason.NONE):
        """Create a mock Comment object."""
        comment = Mock(spec=Comment)
        comment.id = comment_id
        comment.body = body
        comment.score = score
        comment.ups = score + 1
        comment.downs = 1
        comment.created_utc = 1609459200.0  # 2021-01-01 00:00:00
        comment.edited = False
        comment.is_submitter = False
        comment.distinguished = distinguished.value if distinguished != DistinguishedStatus.NONE else None
        comment.stickied = False
        comment.gilded = 0
        comment.controversiality = 0
        comment.permalink = f"/r/test/comments/abc123/_/{comment_id}"
        comment.replies = []
        comment.collapsed = False
        comment.collapsed_reason = collapsed_reason.value if collapsed_reason != CollapsedReason.NONE else None

        # Mock the parent() method to avoid infinite loops in _get_comment_depth
        comment.parent = Mock(return_value=None)

        if is_deleted:
            comment.author = None
            comment.body = CommentBodyStatus.DELETED.value
        elif is_removed:
            comment.author = Mock()
            comment.author.name = author_name
            comment.author.id = f"{author_name}_id"
            comment.body = CommentBodyStatus.REMOVED.value
        else:
            comment.author = Mock()
            comment.author.name = author_name
            comment.author.id = f"{author_name}_id"

        if parent_id:
            comment.parent_id = f"{RedditObjectPrefix.COMMENT.value}{parent_id}"
        else:
            comment.parent_id = f"{RedditObjectPrefix.SUBMISSION.value}submission"

        return comment

    def _create_mock_submission(self, submission_id="test123"):
        """Create a mock Submission object."""
        submission = Mock(spec=Submission)
        submission.id = submission_id
        submission.comments = Mock()
        submission.comments.list = Mock(return_value=[])
        submission.comments.replace_more = Mock()
        return submission

    def test_init(self):
        """Test CommentFetcher initialization."""
        self.assertIsNotNone(self.fetcher.reddit)
        self.assertEqual(self.fetcher.max_retries, 2)
        self.assertEqual(self.fetcher.retry_delay, 0.1)
        self.assertIsNone(self.fetcher.replace_more_limit)
        self.assertEqual(self.fetcher.replace_more_threshold, 10)

    def test_fetch_simple_comments(self):
        """Test fetching simple comments without nesting."""
        submission = self._create_mock_submission()

        # Create mock comments
        comment1 = self._create_mock_comment("comment1", "user1", "First comment")
        comment2 = self._create_mock_comment("comment2", "user2", "Second comment")

        submission.comments.list.return_value = [comment1, comment2]
        submission.comments.__iter__ = Mock(return_value=iter([comment1, comment2]))

        comments = self.fetcher.fetch_submission_comments(submission, flatten=True)

        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0][CommentField.ID], 'comment1')
        self.assertEqual(comments[0][CommentField.AUTHOR], 'user1')
        self.assertEqual(comments[0][CommentField.BODY], 'First comment')
        self.assertEqual(comments[1][CommentField.ID], 'comment2')
        self.assertEqual(comments[1][CommentField.AUTHOR], 'user2')

    def test_fetch_nested_comments(self):
        """Test fetching nested comment structure."""
        submission = self._create_mock_submission()

        # Create nested comment structure
        parent_comment = self._create_mock_comment("parent", "user1", "Parent comment")
        child_comment = self._create_mock_comment(
            "child", "user2", "Child comment",
            parent_id="parent", depth=1
        )

        parent_comment.replies = [child_comment]
        submission.comments.__iter__ = Mock(return_value=iter([parent_comment]))

        comments = self.fetcher.fetch_submission_comments(submission, flatten=False)

        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0][CommentField.ID], 'parent')
        self.assertEqual(comments[0][CommentField.REPLIES][0][CommentField.ID], 'child')
        self.assertEqual(comments[0][CommentField.REPLIES][0][CommentField.PARENT_ID], 'parent')

    def test_handle_deleted_comments(self):
        """Test handling of deleted comments."""
        submission = self._create_mock_submission()

        normal_comment = self._create_mock_comment("normal", "user1", "Normal comment")
        deleted_comment = self._create_mock_comment("deleted", is_deleted=True)

        submission.comments.list.return_value = [normal_comment, deleted_comment]
        submission.comments.__iter__ = Mock(return_value=iter([normal_comment, deleted_comment]))

        # Without including deleted
        comments = self.fetcher.fetch_submission_comments(submission, include_deleted=False)
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0][CommentField.ID], 'normal')

        # With including deleted
        comments = self.fetcher.fetch_submission_comments(submission, include_deleted=True)
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[1][CommentField.AUTHOR], CommentBodyStatus.DELETED.value)
        self.assertTrue(comments[1][CommentField.IS_DELETED])

    def test_handle_removed_comments(self):
        """Test handling of removed comments."""
        submission = self._create_mock_submission()

        normal_comment = self._create_mock_comment("normal", "user1", "Normal comment")
        removed_comment = self._create_mock_comment("removed", "user1", is_removed=True)

        submission.comments.list.return_value = [normal_comment, removed_comment]
        submission.comments.__iter__ = Mock(return_value=iter([normal_comment, removed_comment]))

        comments = self.fetcher.fetch_submission_comments(submission, include_deleted=True)

        self.assertEqual(len(comments), 2)
        self.assertTrue(comments[1][CommentField.IS_REMOVED])
        self.assertEqual(comments[1][CommentField.BODY], CommentBodyStatus.REMOVED.value)

    def test_replace_more_comments(self):
        """Test replace_more functionality."""
        submission = self._create_mock_submission()

        # Mock successful replace_more
        submission.comments.replace_more.return_value = None

        self.fetcher._replace_more_comments(submission)

        submission.comments.replace_more.assert_called_once_with(
            limit=None,
            threshold=10
        )

    def test_replace_more_with_retry(self):
        """Test replace_more with retry on failure."""
        submission = self._create_mock_submission()

        # Mock failure then success
        submission.comments.replace_more.side_effect = [
            PRAWException("API Error"),
            None
        ]

        with patch('time.sleep'):  # Mock sleep to speed up test
            self.fetcher._replace_more_comments(submission)

        self.assertEqual(submission.comments.replace_more.call_count, 2)

    def test_replace_more_max_retries_exceeded(self):
        """Test replace_more failing after max retries."""
        submission = self._create_mock_submission()

        # Mock continuous failures
        submission.comments.replace_more.side_effect = PRAWException("API Error")

        with patch('time.sleep'):  # Mock sleep to speed up test
            with self.assertRaises(PRAWException):
                self.fetcher._replace_more_comments(submission)

        self.assertEqual(submission.comments.replace_more.call_count, 2)

    def test_stream_comments(self):
        """Test streaming comments functionality."""
        submission = self._create_mock_submission()

        comment1 = self._create_mock_comment("comment1", "user1", "First")
        comment2 = self._create_mock_comment("comment2", "user2", "Second")

        submission.comments.__iter__ = Mock(return_value=iter([comment1, comment2]))

        streamed = list(self.fetcher.fetch_submission_comments_stream(submission))

        self.assertEqual(len(streamed), 2)
        self.assertEqual(streamed[0][CommentField.ID], 'comment1')
        self.assertEqual(streamed[1][CommentField.ID], 'comment2')

    def test_process_comment_with_all_attributes(self):
        """Test processing a comment with all attributes."""
        comment = self._create_mock_comment(
            "test_id", "test_user", "Test body", score=42,
            distinguished=DistinguishedStatus.MODERATOR,
            collapsed_reason=CollapsedReason.CROWD_CONTROL
        )
        comment.edited = 1609462800.0
        comment.is_submitter = True
        comment.stickied = True
        comment.gilded = 2
        comment.collapsed = True
        comment.controversiality = 1

        result = self.fetcher._process_comment(
            comment,
            submission_id="sub123",
            parent_id="parent456",
            depth=2
        )

        self.assertEqual(result[CommentField.ID], 'test_id')
        self.assertEqual(result[CommentField.SUBMISSION_ID], 'sub123')
        self.assertEqual(result[CommentField.PARENT_ID], 'parent456')
        self.assertEqual(result[CommentField.AUTHOR], 'test_user')
        self.assertEqual(result[CommentField.BODY], 'Test body')
        self.assertEqual(result[CommentField.SCORE], 42)
        self.assertTrue(result[CommentField.IS_SUBMITTER])
        self.assertEqual(result[CommentField.DISTINGUISHED], DistinguishedStatus.MODERATOR)
        self.assertTrue(result[CommentField.STICKIED])
        self.assertEqual(result[CommentField.GILDED], 2)
        self.assertEqual(result[CommentField.DEPTH], 2)
        self.assertIsNotNone(result[CommentField.PERMALINK])
        self.assertIsNotNone(result[CommentField.CREATED_UTC])
        self.assertIsNotNone(result[CommentField.RETRIEVED_AT])

    def test_process_comment_error_handling(self):
        """Test error handling in comment processing."""
        comment = Mock(spec=Comment)
        comment.id = "test_id"
        # Simulate an attribute error
        type(comment).body = PropertyMock(side_effect=AttributeError("Missing attribute"))

        result = self.fetcher._process_comment(comment, "sub123")

        self.assertIsNone(result)

    def test_get_comment_depth(self):
        """Test calculating comment depth."""
        # Create a chain of comments
        submission = self._create_mock_submission()

        grandparent = self._create_mock_comment("gp", depth=0)
        parent = self._create_mock_comment("p", depth=1)
        child = self._create_mock_comment("c", depth=2)

        # Mock the parent chain
        child.parent = Mock(return_value=parent)
        parent.parent = Mock(return_value=grandparent)
        grandparent.parent = Mock(return_value=submission)

        depth = self.fetcher._get_comment_depth(child)
        self.assertEqual(depth, 2)

    def test_comment_stats(self):
        """Test calculating comment statistics."""
        comments = [
            {
                CommentField.AUTHOR: 'user1',
                CommentField.SCORE: 10,
                CommentField.DEPTH: 0,
                CommentField.GILDED: 1,
                CommentField.IS_DELETED: False,
                CommentField.IS_REMOVED: False
            },
            {
                CommentField.AUTHOR: 'user2',
                CommentField.SCORE: 20,
                CommentField.DEPTH: 1,
                CommentField.GILDED: 0,
                CommentField.IS_DELETED: False,
                CommentField.IS_REMOVED: False
            },
            {
                CommentField.AUTHOR: CommentBodyStatus.DELETED.value,
                CommentField.SCORE: 0,
                CommentField.DEPTH: 0,
                CommentField.GILDED: 0,
                CommentField.IS_DELETED: True,
                CommentField.IS_REMOVED: False
            },
            {
                CommentField.AUTHOR: 'user1',  # Duplicate author
                CommentField.SCORE: 5,
                CommentField.DEPTH: 2,
                CommentField.GILDED: 2,
                CommentField.IS_DELETED: False,
                CommentField.IS_REMOVED: True
            }
        ]

        stats = self.fetcher.get_comment_stats(comments)

        self.assertEqual(stats[CommentStatField.TOTAL_COMMENTS], 4)
        self.assertEqual(stats[CommentStatField.UNIQUE_AUTHORS], 2)  # user1 and user2
        self.assertEqual(stats[CommentStatField.DELETED_COMMENTS], 1)
        self.assertEqual(stats[CommentStatField.REMOVED_COMMENTS], 1)
        self.assertEqual(stats[CommentStatField.AVERAGE_SCORE], 8.75)  # (10+20+0+5)/4
        self.assertEqual(stats[CommentStatField.MAX_DEPTH], 2)
        self.assertEqual(stats[CommentStatField.GILDED_COMMENTS], 3)  # 1+0+0+2

    def test_empty_comment_stats(self):
        """Test statistics for empty comment list."""
        stats = self.fetcher.get_comment_stats([])

        self.assertEqual(stats[CommentStatField.TOTAL_COMMENTS], 0)
        self.assertEqual(stats[CommentStatField.UNIQUE_AUTHORS], 0)
        self.assertEqual(stats[CommentStatField.AVERAGE_SCORE], 0)

    def test_more_comments_filtering(self):
        """Test that MoreComments objects are filtered out."""
        submission = self._create_mock_submission()

        comment = self._create_mock_comment("real_comment")
        more = Mock(spec=MoreComments)

        submission.comments.list.return_value = [comment, more]
        submission.comments.__iter__ = Mock(return_value=iter([comment, more]))

        comments = self.fetcher.fetch_submission_comments(submission)

        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0][CommentField.ID], 'real_comment')


class TestCommentFetcherIntegration(unittest.TestCase):
    """Integration tests for CommentFetcher."""

    def setUp(self):
        """Set up integration test fixtures."""
        self.reddit_client = Mock(spec=praw.Reddit)
        self.fetcher = CommentFetcher(
            reddit_client=self.reddit_client,
            max_retries=3,
            retry_delay=0.01
        )

    def test_complex_comment_tree(self):
        """Test fetching a complex comment tree."""
        submission = Mock(spec=Submission)
        submission.id = "complex_sub"
        submission.comments = Mock()

        # Create a complex tree structure
        # Level 0
        top1 = Mock(spec=Comment)
        top1.id = "top1"
        top1.author = Mock()
        top1.author.name = "user1"
        top1.author.id = "user1_id"
        top1.body = "Top level 1"
        top1.score = 100
        top1.ups = 101
        top1.downs = 1
        top1.created_utc = 1609459200.0
        top1.edited = False
        top1.is_submitter = False
        top1.distinguished = None
        top1.stickied = False
        top1.gilded = 0
        top1.controversiality = 0
        top1.permalink = "/r/test/comments/sub/top1"
        top1.parent_id = f"{RedditObjectPrefix.SUBMISSION.value}complex_sub"
        top1.parent = Mock(return_value=submission)

        # Level 1
        reply1 = Mock(spec=Comment)
        reply1.id = "reply1"
        reply1.author = Mock()
        reply1.author.name = "user2"
        reply1.author.id = "user2_id"
        reply1.body = "Reply to top1"
        reply1.score = 50
        reply1.ups = 51
        reply1.downs = 1
        reply1.created_utc = 1609459300.0
        reply1.edited = False
        reply1.is_submitter = False
        reply1.distinguished = None
        reply1.stickied = False
        reply1.gilded = 0
        reply1.controversiality = 0
        reply1.permalink = "/r/test/comments/sub/reply1"
        reply1.parent_id = f"{RedditObjectPrefix.COMMENT.value}top1"
        reply1.parent = Mock(return_value=top1)
        reply1.replies = []

        # Level 2
        nested_reply = Mock(spec=Comment)
        nested_reply.id = "nested"
        nested_reply.author = Mock()
        nested_reply.author.name = "user3"
        nested_reply.author.id = "user3_id"
        nested_reply.body = "Nested reply"
        nested_reply.score = 25
        nested_reply.ups = 26
        nested_reply.downs = 1
        nested_reply.created_utc = 1609459400.0
        nested_reply.edited = False
        nested_reply.is_submitter = False
        nested_reply.distinguished = None
        nested_reply.stickied = False
        nested_reply.gilded = 1
        nested_reply.controversiality = 0
        nested_reply.permalink = "/r/test/comments/sub/nested"
        nested_reply.parent_id = f"{RedditObjectPrefix.COMMENT.value}reply1"
        nested_reply.parent = Mock(return_value=reply1)
        nested_reply.replies = []

        # Set up relationships
        top1.replies = [reply1]
        reply1.replies = [nested_reply]

        submission.comments.__iter__ = Mock(return_value=iter([top1]))
        submission.comments.replace_more = Mock()

        # Test tree structure
        comments = self.fetcher.fetch_submission_comments(submission, flatten=False)

        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0][CommentField.ID], 'top1')
        self.assertEqual(comments[0][CommentField.DEPTH], 0)

        self.assertEqual(len(comments[0][CommentField.REPLIES]), 1)
        self.assertEqual(comments[0][CommentField.REPLIES][0][CommentField.ID], 'reply1')
        self.assertEqual(comments[0][CommentField.REPLIES][0][CommentField.PARENT_ID], 'top1')
        self.assertEqual(comments[0][CommentField.REPLIES][0][CommentField.DEPTH], 1)

        self.assertEqual(len(comments[0][CommentField.REPLIES][0][CommentField.REPLIES]), 1)
        self.assertEqual(comments[0][CommentField.REPLIES][0][CommentField.REPLIES][0][CommentField.ID], 'nested')
        self.assertEqual(comments[0][CommentField.REPLIES][0][CommentField.REPLIES][0][CommentField.PARENT_ID], 'reply1')
        self.assertEqual(comments[0][CommentField.REPLIES][0][CommentField.REPLIES][0][CommentField.DEPTH], 2)

    def test_large_comment_batch(self):
        """Test handling a large number of comments."""
        submission = Mock(spec=Submission)
        submission.id = "large_batch"
        submission.comments = Mock()

        # Create 100 comments
        comments = []
        for i in range(100):
            comment = Mock(spec=Comment)
            comment.id = f"comment_{i}"
            comment.author = Mock()
            comment.author.name = f"user_{i % 10}"  # 10 unique users
            comment.author.id = f"user_{i % 10}_id"
            comment.body = f"Comment number {i}"
            comment.score = i
            comment.ups = i + 1
            comment.downs = 1
            comment.created_utc = 1609459200.0 + i
            comment.edited = False
            comment.is_submitter = i % 20 == 0
            comment.distinguished = None
            comment.stickied = False
            comment.gilded = 1 if i % 25 == 0 else 0
            comment.controversiality = i % 2
            comment.permalink = f"/r/test/comments/sub/comment_{i}"
            comment.parent_id = f"{RedditObjectPrefix.SUBMISSION.value}large_batch"
            comment.parent = Mock(return_value=submission)  # Add parent method
            comment.replies = []
            comments.append(comment)

        submission.comments.list.return_value = comments
        submission.comments.__iter__ = Mock(return_value=iter(comments))
        submission.comments.replace_more = Mock()

        fetched = self.fetcher.fetch_submission_comments(submission)

        self.assertEqual(len(fetched), 100)

        # Verify stats
        stats = self.fetcher.get_comment_stats(fetched)
        self.assertEqual(stats[CommentStatField.TOTAL_COMMENTS], 100)
        self.assertEqual(stats[CommentStatField.UNIQUE_AUTHORS], 10)
        self.assertEqual(stats[CommentStatField.GILDED_COMMENTS], 4)  # 0, 25, 50, 75


if __name__ == '__main__':
    unittest.main()