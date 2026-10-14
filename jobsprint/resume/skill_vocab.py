"""A bundled tech-keyword vocabulary used, together with the user's own
profile Skills, to extract candidate skills from an uploaded resume. This
only feeds the job/resume match scorer (jobsprint/resume/matcher.py) — the
profile's Skills dict remains the source of truth for KB answers."""

COMMON_TECH_SKILLS = [
    # languages
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Golang", "C++", "C#",
    "Ruby", "PHP", "Rust", "Scala", "Kotlin", "Bash", "Shell Scripting", "PowerShell",
    # cloud
    "AWS", "Azure", "GCP", "Google Cloud", "EC2", "S3", "Lambda", "CloudFormation",
    "IAM", "VPC", "EKS", "AKS", "GKE", "Cloud Functions",
    # devops / infra
    "DevOps", "SRE", "Site Reliability Engineering", "Docker", "Kubernetes",
    "Terraform", "Ansible", "Puppet", "Chef", "CI/CD", "Jenkins", "GitLab",
    "GitLab CI", "GitHub Actions", "CircleCI", "ArgoCD", "Helm", "Vagrant",
    "Infrastructure as Code", "Linux", "Unix", "Nginx", "Apache", "HAProxy",
    # observability
    "Prometheus", "Grafana", "ELK Stack", "Elasticsearch", "Logstash", "Kibana",
    "Datadog", "New Relic", "Splunk", "CloudWatch",
    # databases
    "MySQL", "PostgreSQL", "MongoDB", "Redis", "Cassandra", "DynamoDB", "Oracle",
    "SQL Server", "SQLite", "Elasticsearch",
    # web / frameworks
    "React", "Angular", "Vue.js", "Node.js", "Django", "Flask", "FastAPI",
    "Spring Boot", "Express.js", ".NET", "REST API", "GraphQL", "Microservices",
    # data / ml
    "Machine Learning", "Deep Learning", "TensorFlow", "PyTorch", "Pandas",
    "NumPy", "Data Engineering", "ETL", "Apache Kafka", "Apache Spark", "Airflow",
    # tools / practices
    "Git", "Jira", "Confluence", "Agile", "Scrum", "Kanban", "TDD", "Networking",
    "Security", "DevSecOps", "Load Balancing", "Monitoring", "Automation",
]
