from setuptools import setup, find_packages

setup(name='owlsensor',
      version='0.4.2',
      description='Library to read data from OWL Energy meters',
      long_description='This package is designed for integrating into Home Assistant a serial-connected OWL energy meter.',
      long_description_content_type = 'text/x-rst',
      url='https://github.com/PBrunot/owlsensor',
      author='Pascal Brunot',
      author_email='pbr-dev@gmail.com',
      license='MIT',
      classifiers=[
          'Development Status :: 4 - Beta',
          'Intended Audience :: Developers',
          'Topic :: System :: Hardware :: Hardware Drivers',
          'License :: OSI Approved :: MIT License',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.10'
      ],
      packages=find_packages(),
      install_requires=['pyserial-asyncio-fast>=0.13'],
      keywords='serial owl cm160 energy_meter homeautomation',
      zip_safe=False)
