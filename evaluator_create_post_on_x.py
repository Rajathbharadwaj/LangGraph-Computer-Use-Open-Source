
import json

def perform_eval(run):
    '''Check if create_post_on_x tool succeeded'''

    # Check if this run called the create_post_on_x tool
    if run.get('run_type') != 'tool':
        return None

    if run.get('name') != 'create_post_on_x' and run.get('name') != '_styled_create_post_on_x':
        return None

    # Get the tool output
    outputs = run.get('outputs', {})
    output_text = str(outputs)

    # Success indicators
    success_keywords = [
        'successfully posted',
        'post created',
        'posted successfully',
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
        return {"post_success": 0, "post_working": False}
    elif has_success:
        return {"post_success": 1, "post_working": True}
    else:
        return {"post_success": 0.5, "post_working": None}
