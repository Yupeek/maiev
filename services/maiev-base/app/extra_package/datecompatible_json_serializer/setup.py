# -*- coding: utf-8 -*-
from setuptools import setup

setup(
    name='datecompatible_json_serializer',
    description="json serializer compatible with datetime",
    py_modules=['datecompatible_json_serializer'],
    entry_points={
        'kombu.serializers': [
            'json_datecompatible = datecompatible_json_serializer:register_args'
        ]
    }
)
