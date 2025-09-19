"""Enums for Reddit data fetching."""

from enum import Enum, auto


class CommentField(str, Enum):
    """Field names for comment dictionaries."""
    ID = 'id'
    SUBMISSION_ID = 'submission_id'
    PARENT_ID = 'parent_id'
    AUTHOR = 'author'
    AUTHOR_ID = 'author_id'
    BODY = 'body'
    BODY_HTML = 'body_html'
    SCORE = 'score'
    UPS = 'ups'
    DOWNS = 'downs'
    CREATED_UTC = 'created_utc'
    EDITED = 'edited'
    IS_SUBMITTER = 'is_submitter'
    DISTINGUISHED = 'distinguished'
    STICKIED = 'stickied'
    GILDED = 'gilded'
    COLLAPSED = 'collapsed'
    COLLAPSED_REASON = 'collapsed_reason'
    CONTROVERSIALITY = 'controversiality'
    DEPTH = 'depth'
    PERMALINK = 'permalink'
    RETRIEVED_AT = 'retrieved_at'
    IS_DELETED = 'is_deleted'
    IS_REMOVED = 'is_removed'
    REPLIES = 'replies'


class CommentStatField(str, Enum):
    """Field names for comment statistics dictionaries."""
    TOTAL_COMMENTS = 'total_comments'
    UNIQUE_AUTHORS = 'unique_authors'
    DELETED_COMMENTS = 'deleted_comments'
    REMOVED_COMMENTS = 'removed_comments'
    AVERAGE_SCORE = 'average_score'
    MAX_DEPTH = 'max_depth'
    GILDED_COMMENTS = 'gilded_comments'


class CommentBodyStatus(str, Enum):
    """Special values for comment body text."""
    DELETED = '[deleted]'
    REMOVED = '[removed]'
    NORMAL = 'normal'  # For regular comments


class DistinguishedStatus(str, Enum):
    """Types of distinguished users in Reddit."""
    NONE = None
    MODERATOR = 'moderator'
    ADMIN = 'admin'
    SPECIAL = 'special'


class RedditObjectPrefix(str, Enum):
    """Reddit object type prefixes."""
    COMMENT = 't1_'
    SUBMISSION = 't3_'
    USER = 't2_'
    MESSAGE = 't4_'
    SUBREDDIT = 't5_'
    AWARD = 't6_'


class CollapsedReason(str, Enum):
    """Reasons why a comment might be collapsed."""
    NONE = None
    CROWD_CONTROL = 'crowd control'
    COMMENT_SCORE_BELOW_THRESHOLD = 'comment score below threshold'
    NEW_USER = 'new user'
    POTENTIALLY_TOXIC = 'potentially toxic'
    MANUALLY_COLLAPSED = 'manually collapsed'


class FetchMode(str, Enum):
    """Modes for fetching comments."""
    FLAT = 'flat'
    TREE = 'tree'
    STREAM = 'stream'


class CommentDepth(Enum):
    """Special depth values for comments."""
    TOP_LEVEL = 0
    MAX_VISIBLE = 10  # Reddit's default max visible depth
    UNLIMITED = -1  # For no depth limit


class ErrorType(str, Enum):
    """Types of errors that can occur during fetching."""
    API_ERROR = 'api_error'
    RATE_LIMIT = 'rate_limit'
    AUTHENTICATION = 'authentication'
    NOT_FOUND = 'not_found'
    TIMEOUT = 'timeout'
    UNKNOWN = 'unknown'


class FetchStatus(str, Enum):
    """Status of fetch operations."""
    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    FAILED = 'failed'
    PARTIAL = 'partial'  # Some data fetched but not all