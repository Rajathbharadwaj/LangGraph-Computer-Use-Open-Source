
import json

def perform_eval(run):
    '''Check if like_post tool succeeded'''

    # Check if this run called the like_post tool
    if run.get('run_type') != 'tool':
        return None

    if run.get('name') != 'like_post':
        return None

    # Get the tool output
    outputs = run.get('outputs', {})
    output_text = str(outputs)

    # Success indicators
    success_keywords = [
        'successfully liked',
        'liked post',
        'like successful',
        '✅',
        '❤️'
    ]

    # Failure indicators
    failure_keywords = [
        'failed',
        'error',
        'could not',
        'unable to',
        'already liked',
        '❌'
    ]

    # Check for success
    has_success = any(keyword.lower() in output_text.lower() for keyword in success_keywords)
    has_failure = any(keyword.lower() in output_text.lower() for keyword in failure_keywords)

    if has_failure:
        return {"like_success": 0, "like_working": False}
    elif has_success:
        return {"like_success": 1, "like_working": True}
    else:
        return {"like_success": 0.5, "like_working": None}
