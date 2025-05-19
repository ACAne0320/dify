"""
Workflow Schedule Task
"""

import json
import logging
from datetime import datetime

import app
from extensions.ext_database import db
from libs.cron_helper import calculate_next_run_time
from models.enums import WorkflowRunTriggeredFrom
from models.workflow_schedule import WorkflowSchedule
from services.workflow_scheduler_service import WorkflowRunnerService

_logger = logging.getLogger(__name__)


# This function definition is removed as we now import calculate_next_run_time from libs.cron_helper


@app.celery.task(queue="workflow_schedule")
def execute_scheduled_workflow(schedule_id):
    """
    Execute a scheduled workflow

    Args:
        schedule_id (str): Workflow schedule ID
    """
    _logger.info(f"Starting execution of scheduled workflow: {schedule_id}")

    # Get the schedule first, outside of try block
    schedule = db.session.query(WorkflowSchedule).filter(WorkflowSchedule.id == schedule_id).first()

    if not schedule:
        _logger.error(f"Schedule not found: {schedule_id}")
        return

    _logger.info(f"Found schedule: {schedule.name} (ID: {schedule.id}, workflow_id: {schedule.workflow_id})")

    if not schedule.is_active:
        _logger.info(f"Schedule is not active: {schedule_id}")
        return

    # Track whether workflow execution was successful
    execution_success = False
    workflow_run_id = None
    execution_error = None

    try:
        # Get workflow inputs
        inputs = {}
        if schedule.inputs:
            try:
                _logger.info(f"Parsing inputs for schedule: {schedule_id}")
                inputs = json.loads(schedule.inputs)
                _logger.info(f"Inputs parsed successfully: {inputs}")
            except json.JSONDecodeError:
                # Even with invalid inputs, we should update the schedule times
                execution_error = f"Invalid inputs JSON: {schedule.inputs}"

        if not execution_error:
            # Execute workflow
            _logger.info(f"Creating WorkflowRunnerService for schedule: {schedule_id}")
            workflow_runner_service = WorkflowRunnerService()

            # Execute workflow using the workflow runner service
            _logger.info(f"Running workflow for schedule: {schedule_id}, workflow_id: {schedule.workflow_id}")
            workflow_run = workflow_runner_service.run_scheduled_workflow(
                tenant_id=schedule.tenant_id,
                app_id=schedule.app_id,
                workflow_id=schedule.workflow_id,
                inputs=inputs,
                created_by=schedule.created_by,
                triggered_from=WorkflowRunTriggeredFrom.SCHEDULE.value,
            )

            workflow_run_id = workflow_run.id
            _logger.info(f"Workflow run created with ID: {workflow_run_id}, now updating schedule")
            execution_success = True

    except Exception as e:
        _logger.error(f"Error executing scheduled workflow {schedule_id}: {str(e)}", exc_info=True)

    try:
        # Always update last run time and calculate next run time, even if execution failed
        _logger.info(f"Updating schedule times for: {schedule_id}")

        # Update last run time
        schedule.last_run_at = datetime.utcnow()

        # Calculate next run time
        _logger.info(f"Calculating next run time for schedule: {schedule_id}")
        schedule.next_run_at = calculate_next_run_time(schedule.cron_expression, schedule.timezone)

        _logger.info(f"Next run time calculated: {schedule.next_run_at}")
        db.session.commit()

    except Exception as e:
        db.session.rollback()


@app.celery.task(queue="workflow_schedule")
def check_workflow_schedules():
    """
    Check for workflow schedules that need to be executed
    """
    _logger.info("Checking workflow schedules - TASK STARTED")

    try:
        # Get current time
        now = datetime.utcnow()
        _logger.info(f"Current time: {now}")

        # Get all schedules to verify the table exists and is accessible
        all_schedules = db.session.query(WorkflowSchedule).all()
        _logger.info(f"Total schedules in database: {len(all_schedules)}")

        # Get active schedules
        active_schedules = db.session.query(WorkflowSchedule).filter(WorkflowSchedule.is_active == True).all()
        _logger.info(f"Active schedules in database: {len(active_schedules)}")

        # Get all active schedules that are due to run (next_run_at <= now)
        schedules = (
            db.session.query(WorkflowSchedule)
            .filter(WorkflowSchedule.is_active == True, WorkflowSchedule.next_run_at <= now)
            .all()
        )

        _logger.info(f"Found {len(schedules)} schedules to execute")

        # Log details of each due schedule
        for schedule in schedules:
            _logger.info(f"Schedule due: ID={schedule.id}, Name={schedule.name}, NextRun={schedule.next_run_at}")

        # Execute each schedule synchronously for testing
        for schedule in schedules:
            _logger.info(f"Executing workflow schedule synchronously: {schedule.id}")
            try:
                execute_scheduled_workflow.delay(schedule.id)
                _logger.info(f"Synchronous execution completed for schedule: {schedule.id}")
            except Exception as e:
                _logger.error(f"Error in synchronous execution for schedule {schedule.id}: {str(e)}", exc_info=True)

    except Exception as e:
        _logger.error(f"Error checking workflow schedules: {str(e)}", exc_info=True)
