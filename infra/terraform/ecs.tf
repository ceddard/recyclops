# ALB interno (só acessível dentro da VPC)
resource "aws_lb" "internal" {
  name               = "${var.project_name}-internal"
  internal           = true
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb_internal.id]
  subnets            = aws_subnet.public[*].id
}

resource "aws_lb_listener" "internal" {
  load_balancer_arn = aws_lb.internal.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "Not Found"
      status_code  = "404"
    }
  }
}

# Target Group — recyclops-service (porta 8000)
resource "aws_lb_target_group" "cers_ia" {
  name        = "${var.project_name}-recyclops"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
  }
}

# Target Group — bypass-api (porta 8001)
resource "aws_lb_target_group" "bypass_api" {
  name        = "${var.project_name}-bypass-api"
  port        = 8001
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
  }
}

# Regras de roteamento por path
resource "aws_lb_listener_rule" "cers_ia" {
  listener_arn = aws_lb_listener.internal.arn
  priority     = 5

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.cers_ia.arn
  }

  condition {
    path_pattern {
      values = ["/cers-ia/*"]
    }
  }
}

resource "aws_lb_listener_rule" "bypass_api" {
  listener_arn = aws_lb_listener.internal.arn
  priority     = 20

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.bypass_api.arn
  }

  condition {
    path_pattern {
      values = ["/bypass/*"]
    }
  }
}
