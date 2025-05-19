"""
This module contains service methods for running scheduled workflows.
"""

import json
import logging
from datetime import datetime

from core.workflow.entities.variable_pool import VariablePool
from core.workflow.workflow_entry import WorkflowEntry
from extensions.ext_database import db
from models.enums import CreatedByRole, WorkflowRunTriggeredFrom
from models.model import App, AppMode
from models.workflow import Workflow, WorkflowRun
from services.workflow_service import WorkflowService

_logger = logging.getLogger(__name__)


class WorkflowRunnerService:
    """Service for executing workflows based on schedules"""

    def run_scheduled_workflow(
        self,
        tenant_id: str,
        app_id: str,
        workflow_id: str,
        inputs: dict,
        created_by: str,
        triggered_from: str = WorkflowRunTriggeredFrom.SCHEDULE,
    ):
        """
        Run a workflow based on a schedule

        Args:
            tenant_id: Tenant ID
            app_id: App ID
            workflow_id: Workflow ID
            inputs: Workflow input values
            created_by: User ID who created the schedule
            triggered_from: What triggered this workflow run

        Returns:
            WorkflowRun: The created workflow run
        """
        try:
            # Get app
            app = (
                db.session.query(App)
                .filter(App.id == app_id, App.tenant_id == tenant_id, App.mode == AppMode.WORKFLOW)
                .first()
            )

            if not app:
                _logger.error(f"App not found: {app_id}")
                raise ValueError(f"App not found: {app_id}")

            # Get workflow
            workflow = (
                db.session.query(Workflow)
                .filter(Workflow.id == workflow_id, Workflow.app_id == app_id, Workflow.tenant_id == tenant_id)
                .first()
            )

            if not workflow:
                _logger.error(f"Workflow not found: {workflow_id}")
                raise ValueError(f"Workflow not found: {workflow_id}")

            # Calculate sequence number
            result = db.session.execute(
                db.text(
                    "SELECT MAX(sequence_number) as max_seq FROM workflow_runs "
                    "WHERE tenant_id = :tenant_id AND app_id = :app_id"
                ),
                {"tenant_id": tenant_id, "app_id": app_id},
            ).first()

            sequence_number = (result.max_seq or 0) + 1

            # Create workflow run
            workflow_run = WorkflowRun(
                tenant_id=tenant_id,
                app_id=app_id,
                workflow_id=workflow_id,
                sequence_number=sequence_number,
                type=workflow.type,
                triggered_from=triggered_from,
                version=workflow.version,
                graph=workflow.graph,
                inputs=json.dumps(inputs) if inputs else None,
                status="running",
                created_by_role=CreatedByRole.ACCOUNT,
                created_by=created_by,
                total_steps=0,
            )

            db.session.add(workflow_run)
            db.session.commit()

            # Get workflow service to handle execution
            workflow_service = WorkflowService()

            # Log the workflow execution start
            _logger.info(f"Starting workflow execution for scheduled run: {workflow_run.id}")

            try:
                variable_pool = VariablePool(
                    system_variables={},
                    user_inputs=json.dumps(inputs) if inputs else None,
                    environment_variables=workflow.environment_variables,
                    conversation_variables=[],
                )
                # Initialize workflow entry
                workflow_entry = WorkflowEntry(
                    tenant_id=tenant_id,
                    app_id=app_id,
                    workflow_id=workflow.id,
                    workflow_type=workflow.type,
                    graph=workflow.graph,
                    graph_config=workflow.graph_dict,
                    user_id=created_by,
                    user_from=CreatedByRole.ACCOUNT,
                    invoke_from=WorkflowRunTriggeredFrom.SCHEDULE.value,
                    call_depth=0,
                    variable_pool=variable_pool,
                )

                # Start the workflow execution
                workflow_entry.run_workflow(workflow_run)

                _logger.info(f"Successfully dispatched workflow run: {workflow_run.id}")
            except Exception as e:
                _logger.error(f"Error dispatching workflow run {workflow_run.id}: {str(e)}", exc_info=True)
                # Update workflow run status to failed
                workflow_run.status = "failed"
                workflow_run.error = str(e)
                workflow_run.finished_at = datetime.utcnow()
                db.session.commit()
                raise

            return workflow_run

        except Exception as e:
            db.session.rollback()
            _logger.error(f"Error running scheduled workflow: {str(e)}", exc_info=True)
            raise
