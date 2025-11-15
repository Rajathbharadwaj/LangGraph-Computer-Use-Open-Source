
import json

def perform_eval(run):
    '''Check if comment_on_post tool succeeded'''

    # Check if this run called the comment_on_post tool
    if run.get('run_type') != 'tool':
        return None

    if run.get('name') != 'comment_on_post' and run.get('name') != '_styled_comment_on_post':
        return None

    # Get the tool output
    outputs = run.get('outputs', {})
    output_text = str(outputs)

    # Success indicators
    success_keywords = [
        'successfully posted',
        'comment posted',
        'commented successfully',
        '✅'
    ]

    # Failure indicators
    failure_keywords = [
        'failed',
        'error',
        'could not',
        'unable to',
        '❌'
    ]

    # Check for success
    has_success = any(keyword.lower() in output_text.lower() for keyword in success_keywords)
    has_failure = any(keyword.lower() in output_text.lower() for keyword in failure_keywords)

    if has_failure:
        return {"comment_success": 0, "comment_working": False}
    elif has_success:
        return {"comment_success": 1, "comment_working": True}
    else:
        # Unclear - might need human review
        return {"comment_success": 0.5, "comment_working": None}
