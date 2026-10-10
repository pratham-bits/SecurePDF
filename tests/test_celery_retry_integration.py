from unittest.mock import patch

import pytest

from app.celery_tasks import process_job_task


@pytest.mark.integration
def test_real_celery_retry_configuration():
    """
    Verify that the real Celery task is configured for controlled retries.

    The actual retry lifecycle is exercised by Celery's worker in the
    companion manual integration checkpoint.
    """

    assert process_job_task.max_retries == 2

    # The production task must expose the retry-capable configuration.
    assert process_job_task.name == "securepdf.process_job"