"""Reddit comment fetcher module."""

import logging
from typing import List, Dict, Any, Optional, Generator
from datetime import datetime
import time

import praw
from praw.models import Submission, Comment, MoreComments
from praw.exceptions import PRAWException

from .enums import (
    CommentField,
    CommentStatField,
    CommentBodyStatus,
    DistinguishedStatus,
    RedditObjectPrefix,
    CollapsedReason,
    FetchMode,
    CommentDepth,
    ErrorType,
    FetchStatus
)

logger = logging.getLogger(__name__)


class CommentFetcher:
    """Fetches and processes comments from Reddit submissions."""

    def __init__(self, reddit_client: praw.Reddit,
                 max_retries: int = 3,
                 retry_delay: float = 1.0,
                 replace_more_limit: Optional[int] = None,
                 replace_more_threshold: int = 32):
        """
        Initialize the CommentFetcher.

        Args:
            reddit_client: Authenticated PRAW Reddit instance
            max_retries: Maximum retry attempts for API calls
            retry_delay: Base delay between retries (exponential backoff)
            replace_more_limit: Limit for replace_more() calls (None for all)
            replace_more_threshold: Threshold for replace_more() operation
        """
        self.reddit = reddit_client
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.replace_more_limit = replace_more_limit
        self.replace_more_threshold = replace_more_threshold
        self._comment_cache = {}

    def fetch_submission_comments(self,
                                 submission: Submission,
                                 include_deleted: bool = False,
                                 flatten: bool = True) -> List[Dict[CommentField, Any]]:
        """
        Fetch all comments from a submission.

        Args:
            submission: PRAW Submission object
            include_deleted: Whether to include deleted/removed comments
            flatten: Whether to return flattened list or preserve tree structure

        Returns:
            List of comment dictionaries with metadata
        """
        logger.info(f"Fetching comments for submission {submission.id}")

        # Replace MoreComments objects with actual comments
        self._replace_more_comments(submission)

        # Extract all comments
        comments = []
        if flatten:
            comments = self._extract_comments_flat(
                submission.comments,
                submission_id=submission.id,
                include_deleted=include_deleted
            )
        else:
            comments = self._extract_comments_tree(
                submission.comments,
                submission_id=submission.id,
                parent_id=None,
                depth=0,
                include_deleted=include_deleted
            )

        logger.info(f"Fetched {len(comments)} comments for submission {submission.id}")
        return comments

    def fetch_submission_comments_stream(self,
                                       submission: Submission,
                                       include_deleted: bool = False) -> Generator[Dict[CommentField, Any], None, None]:
        """
        Stream comments from a submission as they're processed.

        Args:
            submission: PRAW Submission object
            include_deleted: Whether to include deleted/removed comments

        Yields:
            Comment dictionaries as they're processed
        """
        logger.info(f"Streaming comments for submission {submission.id}")

        # Replace MoreComments objects
        self._replace_more_comments(submission)

        # Stream comments
        yield from self._stream_comments(
            submission.comments,
            submission_id=submission.id,
            parent_id=None,
            depth=0,
            include_deleted=include_deleted
        )

    def _replace_more_comments(self, submission: Submission) -> None:
        """
        Replace MoreComments objects with actual comments.

        Args:
            submission: PRAW Submission object
        """
        retries = 0
        while retries < self.max_retries:
            try:
                submission.comments.replace_more(
                    limit=self.replace_more_limit,
                    threshold=self.replace_more_threshold
                )
                return
            except PRAWException as e:
                retries += 1
                if retries >= self.max_retries:
                    logger.error(f"Failed to replace more comments after {self.max_retries} attempts: {e}")
                    raise

                delay = self.retry_delay * (2 ** (retries - 1))
                logger.warning(f"Error replacing more comments, retry {retries}/{self.max_retries} after {delay}s: {e}")
                time.sleep(delay)

    def _extract_comments_flat(self,
                              comment_forest,
                              submission_id: str,
                              include_deleted: bool = False) -> List[Dict[CommentField, Any]]:
        """
        Extract comments as a flat list.

        Args:
            comment_forest: PRAW CommentForest object
            submission_id: ID of the parent submission
            include_deleted: Whether to include deleted/removed comments

        Returns:
            Flat list of comment dictionaries
        """
        comments = []
        for comment in comment_forest.list():
            if isinstance(comment, MoreComments):
                continue

            comment_data = self._process_comment(
                comment,
                submission_id=submission_id,
                depth=self._get_comment_depth(comment)
            )

            if comment_data and (include_deleted or not self._is_deleted(comment)):
                comments.append(comment_data)

        return comments

    def _extract_comments_tree(self,
                              comment_forest,
                              submission_id: str,
                              parent_id: Optional[str],
                              depth: int,
                              include_deleted: bool = False) -> List[Dict[CommentField, Any]]:
        """
        Extract comments preserving tree structure.

        Args:
            comment_forest: PRAW CommentForest or list of comments
            submission_id: ID of the parent submission
            parent_id: ID of the parent comment (None for top-level)
            depth: Current depth in comment tree
            include_deleted: Whether to include deleted/removed comments

        Returns:
            List of comment dictionaries with nested replies
        """
        comments = []

        for comment in comment_forest:
            if isinstance(comment, MoreComments):
                continue

            if not include_deleted and self._is_deleted(comment):
                continue

            comment_data = self._process_comment(
                comment,
                submission_id=submission_id,
                parent_id=parent_id,
                depth=depth
            )

            if comment_data:
                # Recursively process replies
                if hasattr(comment, CommentField.REPLIES.value) and comment.replies:
                    comment_data[CommentField.REPLIES] = self._extract_comments_tree(
                        comment.replies,
                        submission_id=submission_id,
                        parent_id=comment.id,
                        depth=depth + 1,
                        include_deleted=include_deleted
                    )
                else:
                    comment_data[CommentField.REPLIES] = []

                comments.append(comment_data)

        return comments

    def _stream_comments(self,
                        comment_forest,
                        submission_id: str,
                        parent_id: Optional[str],
                        depth: int,
                        include_deleted: bool = False) -> Generator[Dict[CommentField, Any], None, None]:
        """
        Stream comments as they're processed.

        Args:
            comment_forest: PRAW CommentForest or list of comments
            submission_id: ID of the parent submission
            parent_id: ID of the parent comment
            depth: Current depth in comment tree
            include_deleted: Whether to include deleted/removed comments

        Yields:
            Comment dictionaries
        """
        for comment in comment_forest:
            if isinstance(comment, MoreComments):
                continue

            if not include_deleted and self._is_deleted(comment):
                continue

            comment_data = self._process_comment(
                comment,
                submission_id=submission_id,
                parent_id=parent_id,
                depth=depth
            )

            if comment_data:
                yield comment_data

                # Recursively process replies
                if hasattr(comment, CommentField.REPLIES.value) and comment.replies:
                    yield from self._stream_comments(
                        comment.replies,
                        submission_id=submission_id,
                        parent_id=comment.id,
                        depth=depth + 1,
                        include_deleted=include_deleted
                    )

    def _process_comment(self,
                        comment: Comment,
                        submission_id: str,
                        parent_id: Optional[str] = None,
                        depth: int = 0) -> Dict[CommentField, Any]:
        """
        Process a single comment into a dictionary.

        Args:
            comment: PRAW Comment object
            submission_id: ID of the parent submission
            parent_id: ID of the parent comment
            depth: Depth in the comment tree

        Returns:
            Dictionary containing comment data
        """
        try:
            # Get parent ID from comment if not provided
            if parent_id is None and hasattr(comment, CommentField.PARENT_ID.value):
                parent_id = comment.parent_id
                if parent_id and parent_id.startswith(RedditObjectPrefix.SUBMISSION.value):
                    parent_id = None  # Top-level comment
                elif parent_id and parent_id.startswith(RedditObjectPrefix.COMMENT.value):
                    parent_id = parent_id[len(RedditObjectPrefix.COMMENT.value):]  # Remove prefix

            collapsed_reason_value = getattr(comment, CommentField.COLLAPSED_REASON.value, None)

            return {
                CommentField.ID: comment.id,
                CommentField.SUBMISSION_ID: submission_id,
                CommentField.PARENT_ID: parent_id,
                CommentField.AUTHOR: comment.author.name if comment.author else CommentBodyStatus.DELETED.value,
                CommentField.AUTHOR_ID: comment.author.id if comment.author else None,
                CommentField.BODY: comment.body,
                CommentField.BODY_HTML: getattr(comment, CommentField.BODY_HTML.value, None),
                CommentField.SCORE: comment.score,
                CommentField.UPS: comment.ups,
                CommentField.DOWNS: comment.downs,
                CommentField.CREATED_UTC: datetime.utcfromtimestamp(comment.created_utc),
                CommentField.EDITED: comment.edited if comment.edited else False,
                CommentField.IS_SUBMITTER: comment.is_submitter,
                CommentField.DISTINGUISHED: DistinguishedStatus(comment.distinguished) if comment.distinguished else DistinguishedStatus.NONE,
                CommentField.STICKIED: comment.stickied,
                CommentField.GILDED: comment.gilded,
                CommentField.COLLAPSED: getattr(comment, CommentField.COLLAPSED.value, False),
                CommentField.COLLAPSED_REASON: CollapsedReason(collapsed_reason_value) if collapsed_reason_value else CollapsedReason.NONE,
                CommentField.CONTROVERSIALITY: getattr(comment, CommentField.CONTROVERSIALITY.value, 0),
                CommentField.DEPTH: depth,
                CommentField.PERMALINK: f"https://reddit.com{comment.permalink}",
                CommentField.RETRIEVED_AT: datetime.now(),
                CommentField.IS_DELETED: self._is_deleted(comment),
                CommentField.IS_REMOVED: self._is_removed(comment)
            }
        except Exception as e:
            logger.error(f"Error processing comment {comment.id}: {e}")
            raise e

    def _get_comment_depth(self, comment: Comment) -> int:
        """
        Calculate the depth of a comment in the tree.

        Args:
            comment: PRAW Comment object

        Returns:
            Depth of the comment (0 for top-level)
        """
        depth = 0
        current = comment

        while hasattr(current, 'parent') and current.parent():
            parent = current.parent()
            if isinstance(parent, Submission):
                break
            current = parent
            depth += 1

        return depth

    def _is_deleted(self, comment: Comment) -> bool:
        """
        Check if a comment is deleted.

        Args:
            comment: PRAW Comment object

        Returns:
            True if comment is deleted
        """
        return comment.author is None and comment.body == CommentBodyStatus.DELETED.value

    def _is_removed(self, comment: Comment) -> bool:
        """
        Check if a comment is removed by moderators.

        Args:
            comment: PRAW Comment object

        Returns:
            True if comment is removed
        """
        return comment.body == CommentBodyStatus.REMOVED.value

    def get_comment_stats(self, comments: List[Dict[CommentField, Any]]) -> Dict[CommentStatField, Any]:
        """
        Calculate statistics for a collection of comments.

        Args:
            comments: List of comment dictionaries

        Returns:
            Dictionary containing comment statistics
        """
        if not comments:
            return {
                CommentStatField.TOTAL_COMMENTS: 0,
                CommentStatField.UNIQUE_AUTHORS: 0,
                CommentStatField.DELETED_COMMENTS: 0,
                CommentStatField.REMOVED_COMMENTS: 0,
                CommentStatField.AVERAGE_SCORE: 0,
                CommentStatField.MAX_DEPTH: 0,
                CommentStatField.GILDED_COMMENTS: 0
            }

        unique_authors = set()
        deleted = 0
        removed = 0
        total_score = 0
        max_depth = 0
        gilded = 0

        for comment in comments:
            if comment[CommentField.AUTHOR] != CommentBodyStatus.DELETED.value:
                unique_authors.add(comment[CommentField.AUTHOR])
            if comment.get(CommentField.IS_DELETED):
                deleted += 1
            if comment.get(CommentField.IS_REMOVED):
                removed += 1
            total_score += comment.get(CommentField.SCORE, 0)
            max_depth = max(max_depth, comment.get(CommentField.DEPTH, 0))
            gilded += comment.get(CommentField.GILDED, 0)

        return {
            CommentStatField.TOTAL_COMMENTS: len(comments),
            CommentStatField.UNIQUE_AUTHORS: len(unique_authors),
            CommentStatField.DELETED_COMMENTS: deleted,
            CommentStatField.REMOVED_COMMENTS: removed,
            CommentStatField.AVERAGE_SCORE: total_score / len(comments) if comments else 0,
            CommentStatField.MAX_DEPTH: max_depth,
            CommentStatField.GILDED_COMMENTS: gilded
        }
