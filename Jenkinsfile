pipeline {
    agent any

    environment {
        PYTHONUNBUFFERED = '1'
        PYTHONDONTWRITEBYTECODE = '1'
    }

    stages {
        stage('Environment Validation') {
            steps {
                echo 'Validating CI execution environment...'
                sh 'python --version || python3 --version'
                sh 'git --version'
            }
        }

        stage('Install Dependencies') {
            steps {
                echo 'Installing required test dependencies...'
                sh 'python -m pip install --upgrade pip'
                sh 'pip install pytest'
            }
        }

        stage('Static Checks') {
            steps {
                echo 'Performing static code checks...'
                sh 'python -m compileall src/ || python3 -m compileall src/'
            }
        }

        stage('Independent Verification Tests') {
            steps {
                echo 'Executing test suite with JUnit XML structured reporting...'
                sh 'python -m pytest tests/ --junitxml=test-results.xml -v'
            }
        }
    }

    post {
        always {
            echo 'Publishing structured JUnit test results...'
            junit testResults: 'test-results.xml', allowEmptyResults: true
        }
        success {
            echo 'CI Verification Passed: All tests succeeded.'
        }
        failure {
            echo 'CI Verification Failed: Test failures detected in workspace.'
        }
    }
}
