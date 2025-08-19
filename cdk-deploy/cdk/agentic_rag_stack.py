"""
Agentic RAG Chatbot CDK Stack
CloudFront -> ALB -> ECS Fargate deployment
"""

import os
from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_logs as logs,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_elasticloadbalancingv2 as elbv2,
    aws_applicationautoscaling as appscaling,
)
from constructs import Construct
from docker_app.config_file import Config


class AgenticRagStack(Stack):
    """Main CDK stack for Agentic RAG Chatbot"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Stack prefix for resource naming
        prefix = Config.STACK_NAME

        # 1. VPC and Networking
        self.vpc = self._create_vpc(prefix)
        
        # 2. Security Groups
        self.alb_sg, self.ecs_sg = self._create_security_groups(prefix)
        
        # 3. ECS Cluster and Service
        self.cluster, self.service = self._create_ecs_service(prefix)
        
        # 4. Application Load Balancer
        self.alb, self.target_group = self._create_load_balancer(prefix)
        
        # 5. CloudFront Distribution
        self.distribution = self._create_cloudfront_distribution(prefix)
        
        # 6. Outputs
        self._create_outputs()

    def _create_vpc(self, prefix: str) -> ec2.Vpc:
        """Create VPC with public and private subnets"""
        vpc = ec2.Vpc(
            self,
            f"{prefix}Vpc",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=2,
            vpc_name=f"{prefix}-vpc",
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )
        return vpc

    def _create_security_groups(self, prefix: str) -> tuple:
        """Create security groups for ALB and ECS"""
        
        # ALB Security Group
        alb_sg = ec2.SecurityGroup(
            self,
            f"{prefix}AlbSecurityGroup",
            vpc=self.vpc,
            security_group_name=f"{prefix}-alb-sg",
            description="Security group for Application Load Balancer",
            allow_all_outbound=True,
        )
        
        # Allow HTTP and HTTPS from anywhere
        alb_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(80),
            description="Allow HTTP from anywhere"
        )
        alb_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(443),
            description="Allow HTTPS from anywhere"
        )

        # ECS Security Group
        ecs_sg = ec2.SecurityGroup(
            self,
            f"{prefix}EcsSecurityGroup",
            vpc=self.vpc,
            security_group_name=f"{prefix}-ecs-sg",
            description="Security group for ECS tasks",
            allow_all_outbound=True,
        )
        
        # Allow traffic from ALB to ECS
        ecs_sg.add_ingress_rule(
            peer=alb_sg,
            connection=ec2.Port.tcp(Config.APP_PORT),
            description="Allow traffic from ALB"
        )

        return alb_sg, ecs_sg

    def _create_ecs_service(self, prefix: str) -> tuple:
        """Create ECS cluster and Fargate service"""
        
        # ECS Cluster
        cluster = ecs.Cluster(
            self,
            f"{prefix}Cluster",
            cluster_name=f"{prefix}-cluster",
            vpc=self.vpc,
            container_insights=True,
        )

        # Task Role - permissions for the application
        task_role = iam.Role(
            self,
            f"{prefix}TaskRole",
            role_name=f"{prefix}-task-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonECSTaskExecutionRolePolicy"),
            ],
        )

        # Add Bedrock permissions
        task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:Retrieve",
                    "bedrock:RetrieveAndGenerate",
                ],
                resources=["*"],
            )
        )

        # Add CloudWatch Logs permissions
        task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=["*"],
            )
        )

        # Execution Role
        execution_role = iam.Role(
            self,
            f"{prefix}ExecutionRole",
            role_name=f"{prefix}-execution-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonECSTaskExecutionRolePolicy"),
            ],
        )

        # Log Group
        log_group = logs.LogGroup(
            self,
            f"{prefix}LogGroup",
            log_group_name=f"/ecs/{prefix}",
            retention=logs.RetentionDays.ONE_WEEK,
        )

        # Task Definition
        task_definition = ecs.FargateTaskDefinition(
            self,
            f"{prefix}TaskDefinition",
            family=f"{prefix}-task",
            cpu=Config.CPU,
            memory_limit_mib=Config.MEMORY,
            task_role=task_role,
            execution_role=execution_role,
        )

        # Container Definition
        container = task_definition.add_container(
            f"{prefix}Container",
            image=ecs.ContainerImage.from_asset("docker_app"),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="ecs",
                log_group=log_group,
            ),
            environment={
                "AWS_REGION": self.region,
                "KB_ID": Config.KB_ID,
                "MODEL_ID": Config.MODEL_ID,
                "LOG_LEVEL": Config.LOG_LEVEL,
                "ENVIRONMENT": "production",
            },
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "/app/healthcheck.sh"],
                interval=Duration.seconds(Config.HEALTH_CHECK_INTERVAL),
                timeout=Duration.seconds(Config.HEALTH_CHECK_TIMEOUT),
                retries=Config.HEALTH_CHECK_RETRIES,
                start_period=Duration.seconds(60),
            ),
        )

        # Port mapping
        container.add_port_mappings(
            ecs.PortMapping(
                container_port=Config.APP_PORT,
                protocol=ecs.Protocol.TCP,
            )
        )

        # Fargate Service
        service = ecs.FargateService(
            self,
            f"{prefix}Service",
            service_name=f"{prefix}-service",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=Config.MIN_CAPACITY,
            security_groups=[self.ecs_sg],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            health_check_grace_period=Duration.seconds(120),
            enable_logging=True,
        )

        # Auto Scaling
        scaling = service.auto_scale_task_count(
            min_capacity=Config.MIN_CAPACITY,
            max_capacity=Config.MAX_CAPACITY,
        )

        # CPU-based scaling
        scaling.scale_on_cpu_utilization(
            f"{prefix}CpuScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(300),
            scale_out_cooldown=Duration.seconds(60),
        )

        # Memory-based scaling
        scaling.scale_on_memory_utilization(
            f"{prefix}MemoryScaling",
            target_utilization_percent=80,
            scale_in_cooldown=Duration.seconds(300),
            scale_out_cooldown=Duration.seconds(60),
        )

        return cluster, service

    def _create_load_balancer(self, prefix: str) -> tuple:
        """Create Application Load Balancer"""
        
        # Application Load Balancer
        alb = elbv2.ApplicationLoadBalancer(
            self,
            f"{prefix}LoadBalancer",
            load_balancer_name=f"{prefix}-alb",
            vpc=self.vpc,
            internet_facing=True,
            security_group=self.alb_sg,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC
            ),
        )

        # Target Group
        target_group = elbv2.ApplicationTargetGroup(
            self,
            f"{prefix}TargetGroup",
            target_group_name=f"{prefix}-tg",
            port=Config.APP_PORT,
            protocol=elbv2.ApplicationProtocol.HTTP,
            vpc=self.vpc,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                enabled=True,
                path="/?health=check",
                protocol=elbv2.Protocol.HTTP,
                port=str(Config.APP_PORT),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
                timeout=Duration.seconds(Config.HEALTH_CHECK_TIMEOUT),
                interval=Duration.seconds(Config.HEALTH_CHECK_INTERVAL),
            ),
        )

        # Listener
        listener = alb.add_listener(
            f"{prefix}Listener",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_target_groups=[target_group],
        )

        # Add custom header check for CloudFront
        listener.add_action(
            f"{prefix}CustomHeaderAction",
            priority=100,
            conditions=[
                elbv2.ListenerCondition.http_header(
                    Config.CUSTOM_HEADER_NAME,
                    [Config.CUSTOM_HEADER_VALUE]
                )
            ],
            action=elbv2.ListenerAction.forward([target_group]),
        )

        # Attach service to target group
        self.service.attach_to_application_target_group(target_group)

        return alb, target_group

    def _create_cloudfront_distribution(self, prefix: str) -> cloudfront.Distribution:
        """Create CloudFront distribution"""
        
        # Origin
        origin = origins.LoadBalancerV2Origin(
            self.alb,
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
            custom_headers={
                Config.CUSTOM_HEADER_NAME: Config.CUSTOM_HEADER_VALUE
            },
        )

        # Distribution
        distribution = cloudfront.Distribution(
            self,
            f"{prefix}Distribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.CORS_S3_ORIGIN,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
            ),
            comment=f"{prefix} CloudFront Distribution",
            enabled=True,
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
        )

        return distribution

    def _create_outputs(self):
        """Create CloudFormation outputs"""
        
        CfnOutput(
            self,
            "CloudFrontURL",
            value=f"https://{self.distribution.distribution_domain_name}",
            description="CloudFront Distribution URL",
        )

        CfnOutput(
            self,
            "LoadBalancerDNS",
            value=self.alb.load_balancer_dns_name,
            description="Application Load Balancer DNS Name",
        )

        CfnOutput(
            self,
            "ECSClusterName",
            value=self.cluster.cluster_name,
            description="ECS Cluster Name",
        )

        CfnOutput(
            self,
            "ECSServiceName",
            value=self.service.service_name,
            description="ECS Service Name",
        )
