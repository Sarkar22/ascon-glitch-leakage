FROM ubuntu:24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ngspice yosys iverilog python3 python3-numpy python3-scipy python3-matplotlib make && rm -rf /var/lib/apt/lists/*
