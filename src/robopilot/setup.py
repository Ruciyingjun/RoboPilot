"""用途：定义 Python/ROS 包元信息、依赖、安装资源及 robopilot 命令行入口。"""

from glob import glob

from setuptools import find_packages, setup

setup(
    name='robopilot',
    version='0.5.0',
    packages=find_packages(exclude=['tests']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/robopilot']),
        ('share/robopilot', ['package.xml']),
        ('share/robopilot/config', glob('config/*.yaml')),
        ('share/robopilot/config', glob('config/*.env.example')),
        ('share/robopilot/examples', glob('examples/*.json')),
        ('share/robopilot/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools', 'PyYAML'],
    tests_require=['pytest'],
    zip_safe=True,
    maintainer='RoboPilot Maintainer',
    maintainer_email='maintainer@example.invalid',
    description='Language-grounded ROS 2 inspection with evidence and spatial observation memory',
    license='Proprietary',
    entry_points={'console_scripts': ['robopilot = robopilot.cli:main']},
)
