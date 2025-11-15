
import json

def perform_eval(run):
    '''Check if unlike_post tool succeeded'''

    # Check if this run called the unlike_post tool
    if run.get('run_type') != 'tool':
        return None

    if run.get('name') != 'unlike_post':
        return None

    # Get the tool output
    outputs = run.get('outputs', {})
    output_text = str(outputs)

    # Success indicators
    success_keywords = [
        'successfully unliked',
        'unliked post',
        'unlike successful',
        '✅'
    ]

    # Failure indicators
    failure_keywords = [
        'failed',
        'error',
        'could not',
        'unable to',
        'not liked',
        '❌'
    ]

    # Check for success
    has_success = any(keyword.lower() in output_text.lower() for keyword in success_keywords)
    has_failure = any(keyword.lower() in output_text.lower() for keyword in failure_keywords)

    if has_failure:
        return {"unlike_success": 0, "unlike_working": False}
    elif has_success:
        return {"unlike_success": 1, "unlike_working": True}
    else:
        return {"unlike_success": 0.5, "unlike_working": None}
