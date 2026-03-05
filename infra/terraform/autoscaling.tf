resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "disabled" # habilitar em prod, custa $$ no PoC
  }
}

# ─────────────────────────────────────────
# SERVIÇO 1: recyclops-service
# ─────────────────────────────────────────
resource "aws_ecs_task_definition" "cers_ia" {
  family                   = "${var.project_name}-recyclops"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"  # 0.5 vCPU para LLM
  memory                   = "1024" # 1 GB para modelos
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "recyclops-service"
    image     = var.cers_ia_image != "" ? var.cers_ia_image : "${aws_ecr_repository.cers_ia.repository_url}:latest"
    essential = true

    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    secrets = [
      { name = "OPENAI_API_KEY", valueFrom = aws_ssm_parameter.openai_api_key.arn }
    ]

    environment = [
      { name = "PORT", value = "8000" }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.cers_ia.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "recyclops"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])
}

resource "aws_ecs_service" "cers_ia" {
  name            = "${var.project_name}-recyclops"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.cers_ia.arn
  launch_type     = "FARGATE"
  desired_count   = 1

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.cers_ia.arn
    container_name   = "recyclops-service"
    container_port   = 8000
  }

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }
}

# ─────────────────────────────────────────
# SERVIÇO 2: accessibility-analyzer (SQS worker)
# ─────────────────────────────────────────
resource "aws_ecs_task_definition" "analyzer" {
  family                   = "${var.project_name}-analyzer"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "1024" # 1 vCPU para análises paralelas
  memory                   = "2048" # 2 GB para buffer de análise
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "accessibility-analyzer"
    image     = var.analyzer_image != "" ? var.analyzer_image : "${aws_ecr_repository.analyzer.repository_url}:latest"
    essential = true

    # Entrypoint para o SQS worker
    command = ["python", "main.py"]

    secrets = [
      { name = "GITHUB_TOKEN",    valueFrom = aws_ssm_parameter.github_token.arn },
      { name = "OPENAI_API_KEY",  valueFrom = aws_ssm_parameter.openai_api_key.arn }
    ]

    environment = [
      { name = "SQS_URL",          value = aws_sqs_queue.accessibility.url },
      { name = "DLQ_URL",          value = aws_sqs_queue.analyzer_dlq.url },
      { name = "CERS_IA_URL",      value = "http://${aws_lb.internal.dns_name}" },
      { name = "BYPASS_API_URL",   value = "http://${aws_lb.internal.dns_name}" },
      { name = "DYNAMODB_REPORTS", value = aws_dynamodb_table.reports.name },
      { name = "DYNAMODB_BYPASS",  value = aws_dynamodb_table.bypass_rules.name },
      { name = "SCORE_THRESHOLD",  value = tostring(var.score_threshold) },
      { name = "AWS_REGION",       value = var.aws_region }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.analyzer.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "analyzer"
      }
    }
  }])
}

resource "aws_ecs_service" "analyzer" {
  name            = "${var.project_name}-analyzer"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.analyzer.arn
  launch_type     = "FARGATE"
  desired_count   = 1

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true
  }

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }
}

# ─────────────────────────────────────────
# SERVIÇO 3: bypass-api
# ─────────────────────────────────────────
resource "aws_ecs_task_definition" "bypass_api" {
  family                   = "${var.project_name}-bypass-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"  # 0.25 vCPU (gerenciamento leve)
  memory                   = "512"  # 512 MB (DynamoDB query e response)
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "bypass-api"
    image     = var.bypass_api_image != "" ? var.bypass_api_image : "${aws_ecr_repository.bypass_api.repository_url}:latest"
    essential = true

    portMappings = [{
      containerPort = 8001
      protocol      = "tcp"
    }]

    environment = [
      { name = "DYNAMODB_BYPASS", value = aws_dynamodb_table.bypass_rules.name },
      { name = "AWS_REGION",      value = var.aws_region },
      { name = "PORT",            value = "8001" }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.bypass_api.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "bypass-api"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8001/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
  }])
}

resource "aws_ecs_service" "bypass_api" {
  name            = "${var.project_name}-bypass-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.bypass_api.arn
  launch_type     = "FARGATE"
  desired_count   = 1

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.bypass_api.arn
    container_name   = "bypass-api"
    container_port   = 8001
  }

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }
}



# ─────────────────────────────────────────
# Auto-scaling do analyzer baseado na fila SQS
# ─────────────────────────────────────────
resource "aws_appautoscaling_target" "analyzer" {
  max_capacity       = 5
  min_capacity       = 1
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.analyzer.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "analyzer_scale_up" {
  name               = "${var.project_name}-analyzer-scale-up"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.analyzer.resource_id
  scalable_dimension = aws_appautoscaling_target.analyzer.scalable_dimension
  service_namespace  = aws_appautoscaling_target.analyzer.service_namespace

  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    cooldown                = 60
    metric_aggregation_type = "Average"

    step_adjustment {
      metric_interval_lower_bound = 0
      scaling_adjustment          = 1
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "sqs_depth" {
  alarm_name          = "${var.project_name}-sqs-depth-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Sum"
  threshold           = 5

  dimensions = {
    QueueName = aws_sqs_queue.accessibility.name
  }

  alarm_actions = [aws_appautoscaling_policy.analyzer_scale_up.arn]
}
