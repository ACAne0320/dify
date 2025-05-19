"""
Workflow Schedule API endpoints
"""

import json

import pytz
from flask import jsonify
from flask_login import current_user
from flask_restful import Resource, reqparse
from werkzeug.exceptions import BadRequest, NotFound

from controllers.console import api
from controllers.console.app.wraps import get_app_model
from controllers.console.wraps import account_initialization_required, setup_required
from extensions.ext_database import db
from libs.cron_helper import calculate_next_run_time, validate_cron_expression
from libs.login import login_required
from models.model import AppMode
from models.workflow import Workflow
from models.workflow_schedule import WorkflowSchedule


class WorkflowScheduleListResource(Resource):
    """
    Workflow schedule list resource
    """

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.WORKFLOW])
    def get(self, app_model):
        """
        Get all schedules for an app
        """
        account = current_user

        schedules = (
            db.session.query(WorkflowSchedule)
            .filter(WorkflowSchedule.tenant_id == account.current_tenant_id, WorkflowSchedule.app_id == app_model.id)
            .all()
        )

        response_data = []
        for schedule in schedules:
            response_data.append(schedule.to_dict())

        return jsonify({"data": response_data})

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.WORKFLOW])
    def post(self, app_model):
        """
        Create a new schedule
        """
        account = current_user

        parser = reqparse.RequestParser()
        parser.add_argument("workflow_id", type=str, required=True, location="json")
        parser.add_argument("name", type=str, required=True, location="json")
        parser.add_argument("description", type=str, location="json")
        parser.add_argument("cron_expression", type=str, required=True, location="json")
        parser.add_argument("timezone", type=str, required=True, location="json")
        parser.add_argument("inputs", type=dict, location="json")
        parser.add_argument("is_active", type=bool, default=True, location="json")

        args = parser.parse_args()

        # Check if workflow exists and belongs to this app
        workflow = (
            db.session.query(Workflow)
            .filter(
                Workflow.id == args["workflow_id"],
                Workflow.app_id == app_model.id,
                Workflow.tenant_id == account.current_tenant_id,
            )
            .first()
        )

        if not workflow:
            raise NotFound("Workflow not found")

        # Validate cron expression
        try:
            validate_cron_expression(args["cron_expression"])
        except ValueError as e:
            raise BadRequest(f"Invalid cron expression: {str(e)}")

        # Validate timezone
        try:
            timezone = pytz.timezone(args["timezone"])
        except pytz.exceptions.UnknownTimeZoneError:
            raise BadRequest(f"Invalid timezone: {args['timezone']}")

        # Calculate next run time
        next_run_at = calculate_next_run_time(args["cron_expression"], args["timezone"])

        # Create schedule
        schedule = WorkflowSchedule(
            tenant_id=account.current_tenant_id,
            app_id=app_model.id,
            workflow_id=args["workflow_id"],
            name=args["name"],
            description=args.get("description"),
            cron_expression=args["cron_expression"],
            timezone=args["timezone"],
            inputs=json.dumps(args.get("inputs", {})) if args.get("inputs") else None,
            is_active=args["is_active"],
            created_by=account.id,
            next_run_at=next_run_at,
            last_run_at=None,
        )

        db.session.add(schedule)
        db.session.commit()

        response_data = schedule.to_dict()
        return jsonify({"data": response_data})


class WorkflowScheduleResource(Resource):
    """
    Single workflow schedule resource
    """

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.WORKFLOW])
    def get(self, app_model, schedule_id):
        """
        Get a specific schedule
        """
        account = current_user

        schedule = (
            db.session.query(WorkflowSchedule)
            .filter(
                WorkflowSchedule.id == schedule_id,
                WorkflowSchedule.tenant_id == account.current_tenant_id,
                WorkflowSchedule.app_id == app_model.id,
            )
            .first()
        )

        if not schedule:
            raise NotFound("Schedule not found")

        response_data = schedule.to_dict()
        return jsonify({"data": response_data})

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.WORKFLOW])
    def put(self, app_model, schedule_id):
        """
        Update a schedule
        """
        account = current_user

        schedule = (
            db.session.query(WorkflowSchedule)
            .filter(
                WorkflowSchedule.id == schedule_id,
                WorkflowSchedule.tenant_id == account.current_tenant_id,
                WorkflowSchedule.app_id == app_model.id,
            )
            .first()
        )

        if not schedule:
            raise NotFound("Schedule not found")

        parser = reqparse.RequestParser()
        parser.add_argument("workflow_id", type=str, location="json")
        parser.add_argument("name", type=str, location="json")
        parser.add_argument("description", type=str, location="json")
        parser.add_argument("cron_expression", type=str, location="json")
        parser.add_argument("timezone", type=str, location="json")
        parser.add_argument("inputs", type=dict, location="json")
        parser.add_argument("is_active", type=bool, location="json")

        args = parser.parse_args()

        # If workflow_id changed, check if new workflow exists and belongs to this app
        if args.get("workflow_id") and args["workflow_id"] != schedule.workflow_id:
            workflow = (
                db.session.query(Workflow)
                .filter(
                    Workflow.id == args["workflow_id"],
                    Workflow.app_id == app_model.id,
                    Workflow.tenant_id == account.current_tenant_id,
                )
                .first()
            )

            if not workflow:
                raise NotFound("Workflow not found")

            schedule.workflow_id = args["workflow_id"]

        # Update fields if provided
        if args.get("name") is not None:
            schedule.name = args["name"]

        if args.get("description") is not None:
            schedule.description = args["description"]

        cron_changed = False
        timezone_changed = False

        if args.get("cron_expression") is not None:
            # Validate cron expression
            try:
                validate_cron_expression(args["cron_expression"])
            except ValueError as e:
                raise BadRequest(f"Invalid cron expression: {str(e)}")

            schedule.cron_expression = args["cron_expression"]
            cron_changed = True

        if args.get("timezone") is not None:
            # Validate timezone
            try:
                timezone = pytz.timezone(args["timezone"])
            except pytz.exceptions.UnknownTimeZoneError:
                raise BadRequest(f"Invalid timezone: {args['timezone']}")

            schedule.timezone = args["timezone"]
            timezone_changed = True

        if args.get("inputs") is not None:
            schedule.inputs = json.dumps(args["inputs"])

        if args.get("is_active") is not None:
            schedule.is_active = args["is_active"]

        # Recalculate next run time if cron or timezone changed
        if cron_changed or timezone_changed:
            schedule.next_run_at = calculate_next_run_time(schedule.cron_expression, schedule.timezone)

        db.session.commit()

        response_data = schedule.to_dict()
        return jsonify({"data": response_data})

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.WORKFLOW])
    def delete(self, app_model, schedule_id):
        """
        Delete a schedule
        """
        account = current_user

        schedule = (
            db.session.query(WorkflowSchedule)
            .filter(
                WorkflowSchedule.id == schedule_id,
                WorkflowSchedule.tenant_id == account.current_tenant_id,
                WorkflowSchedule.app_id == app_model.id,
            )
            .first()
        )

        if not schedule:
            raise NotFound("Schedule not found")

        db.session.delete(schedule)
        db.session.commit()

        return "", 204


class WorkflowScheduleToggleResource(Resource):
    """
    Toggle workflow schedule active status
    """

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.WORKFLOW])
    def post(self, app_model, schedule_id):
        """
        Toggle schedule active status
        """
        account = current_user

        schedule = (
            db.session.query(WorkflowSchedule)
            .filter(
                WorkflowSchedule.id == schedule_id,
                WorkflowSchedule.tenant_id == account.current_tenant_id,
                WorkflowSchedule.app_id == app_model.id,
            )
            .first()
        )

        if not schedule:
            raise NotFound("Schedule not found")

        schedule.is_active = not schedule.is_active

        # If activating, recalculate next run time
        if schedule.is_active:
            schedule.next_run_at = calculate_next_run_time(schedule.cron_expression, schedule.timezone)

        db.session.commit()

        response_data = schedule.to_dict()
        return jsonify({"data": response_data})


# Register API resources
api.add_resource(WorkflowScheduleListResource, "/apps/<uuid:app_id>/workflow/schedules")
api.add_resource(WorkflowScheduleResource, "/apps/<uuid:app_id>/workflow/schedules/<uuid:schedule_id>")
api.add_resource(WorkflowScheduleToggleResource, "/apps/<uuid:app_id>/workflow/schedules/<uuid:schedule_id>/toggle")
