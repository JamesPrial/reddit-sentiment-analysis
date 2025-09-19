#!/usr/bin/env python3
"""Basic test runner for CommentFetcher."""

import sys
import os
from unittest import TestCase, main
from unittest.mock import Mock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetchers.comment import CommentFetcher
from fetchers.enums import CommentField, CommentStatField, CommentBodyStatus, RedditObjectPrefix
import praw
from praw.models import Comment


class BasicCommentFetcherTests(TestCase):
    """Basic tests for CommentFetcher."""

    def setUp(self):
        """Set up test fixtures."""
        self.reddit_client = Mock(spec=praw.Reddit)
        self.fetcher = CommentFetcher(self.reddit_client)

    def test_initialization(self):
        """Test that CommentFetcher initializes correctly."""
        self.assertIsNotNone(self.fetcher)
        self.assertEqual(self.fetcher.reddit, self.reddit_client)
        print("✓ Initialization test passed")

    def test_process_comment(self):
        """Test processing a simple comment."""
        comment = Mock(spec=Comment)
        comment.id = "test123"
        comment.body = "Test comment body"
        comment.score = 42
        comment.ups = 43
        comment.downs = 1
        comment.created_utc = 1609459200.0
        comment.edited = False
        comment.is_submitter = False
        comment.distinguished = None
        comment.stickied = False
        comment.gilded = 0
        comment.permalink = "/r/test/comments/abc/test123"
        comment.parent_id = f"{RedditObjectPrefix.SUBMISSION.value}abc"

        author = Mock()
        author.name = "test_user"
        author.id = "user123"
        comment.author = author

        result = self.fetcher._process_comment(comment, "submission_id")

        self.assertEqual(result[CommentField.ID], 'test123')
        self.assertEqual(result[CommentField.AUTHOR], 'test_user')
        self.assertEqual(result[CommentField.BODY], 'Test comment body')
        self.assertEqual(result[CommentField.SCORE], 42)
        print("✓ Process comment test passed")

    def test_is_deleted_comment(self):
        """Test detection of deleted comments."""
        comment = Mock(spec=Comment)
        comment.author = None
        comment.body = CommentBodyStatus.DELETED.value

        self.assertTrue(self.fetcher._is_deleted(comment))
        print("✓ Deleted comment detection test passed")

    def test_is_removed_comment(self):
        """Test detection of removed comments."""
        comment = Mock(spec=Comment)
        comment.body = CommentBodyStatus.REMOVED.value

        self.assertTrue(self.fetcher._is_removed(comment))
        print("✓ Removed comment detection test passed")

    def test_get_comment_stats_empty(self):
        """Test stats calculation for empty comment list."""
        stats = self.fetcher.get_comment_stats([])

        self.assertEqual(stats[CommentStatField.TOTAL_COMMENTS], 0)
        self.assertEqual(stats[CommentStatField.UNIQUE_AUTHORS], 0)
        self.assertEqual(stats[CommentStatField.AVERAGE_SCORE], 0)
        print("✓ Empty stats test passed")

    def test_get_comment_stats_with_data(self):
        """Test stats calculation with sample data."""
        comments = [
            {CommentField.AUTHOR: 'user1', CommentField.SCORE: 10, CommentField.DEPTH: 0, CommentField.GILDED: 1, CommentField.IS_DELETED: False, CommentField.IS_REMOVED: False},
            {CommentField.AUTHOR: 'user2', CommentField.SCORE: 20, CommentField.DEPTH: 1, CommentField.GILDED: 0, CommentField.IS_DELETED: False, CommentField.IS_REMOVED: False},
            {CommentField.AUTHOR: CommentBodyStatus.DELETED.value, CommentField.SCORE: 0, CommentField.DEPTH: 0, CommentField.GILDED: 0, CommentField.IS_DELETED: True, CommentField.IS_REMOVED: False},
        ]

        stats = self.fetcher.get_comment_stats(comments)

        self.assertEqual(stats[CommentStatField.TOTAL_COMMENTS], 3)
        self.assertEqual(stats[CommentStatField.UNIQUE_AUTHORS], 2)
        self.assertEqual(stats[CommentStatField.DELETED_COMMENTS], 1)
        self.assertEqual(stats[CommentStatField.AVERAGE_SCORE], 10.0)
        print("✓ Stats calculation test passed")


if __name__ == '__main__':
    print("Running basic CommentFetcher tests...\n")
    main(verbosity=2)