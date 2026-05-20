.DEFAULT_GOAL := all

CXX ?= c++
CXXFLAGS ?= -std=c++17 -Wall -Wextra -O2

ROOT_DIR := ..
INCLUDE_DIR := $(ROOT_DIR)/dist/include

UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
  LIB_DIR := $(ROOT_DIR)/dist/shared/mac
  SDK_LIB := $(LIB_DIR)/libbc_revo3_sdk.dylib
  RPATH := -Wl,-rpath,@loader_path/../../dist/shared/mac
else ifeq ($(UNAME_S),Linux)
  LIB_DIR := $(ROOT_DIR)/dist/shared/linux
  SDK_LIB := $(LIB_DIR)/libbc_revo3_sdk.so
  RPATH := -Wl,-rpath,'$$ORIGIN/../../dist/shared/linux'
else
  LIB_DIR := $(ROOT_DIR)/dist/shared/win
  SDK_LIB := $(LIB_DIR)/bc_revo3_sdk.dll
  RPATH :=
endif

INCLUDES := -I$(INCLUDE_DIR)
LDFLAGS := -L$(LIB_DIR) -lbc_revo3_sdk $(RPATH)

COMMON_SRC := common/revo3_common.cpp
TARGETS := demo/auto_detect demo/hand_demo demo/hand_trajectory demo/hand_dfu demo/revo3_motor demo/revo3_touch demo/revo3_monitor demo/revo3_servo

all: $(TARGETS)

demo/auto_detect: demo/auto_detect.cpp $(COMMON_SRC) common/revo3_common.h $(SDK_LIB)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $< $(COMMON_SRC) -o $@ $(LDFLAGS)

demo/hand_demo: demo/hand_demo.cpp $(COMMON_SRC) common/revo3_common.h $(SDK_LIB)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $< $(COMMON_SRC) -o $@ $(LDFLAGS)

demo/hand_trajectory: demo/hand_trajectory.cpp $(COMMON_SRC) common/revo3_common.h $(SDK_LIB)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $< $(COMMON_SRC) -o $@ $(LDFLAGS)

demo/hand_dfu: demo/hand_dfu.cpp $(COMMON_SRC) common/revo3_common.h $(SDK_LIB)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $< $(COMMON_SRC) -o $@ $(LDFLAGS)

demo/revo3_motor: demo/revo3_motor.cpp $(COMMON_SRC) common/revo3_common.h $(SDK_LIB)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $< $(COMMON_SRC) -o $@ $(LDFLAGS)

demo/revo3_touch: demo/revo3_touch.cpp $(COMMON_SRC) common/revo3_common.h $(SDK_LIB)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $< $(COMMON_SRC) -o $@ $(LDFLAGS)

demo/revo3_monitor: demo/revo3_monitor.cpp $(COMMON_SRC) common/revo3_common.h $(SDK_LIB)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $< $(COMMON_SRC) -o $@ $(LDFLAGS)

demo/revo3_servo: demo/revo3_servo.cpp $(COMMON_SRC) common/revo3_common.h $(SDK_LIB)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $< $(COMMON_SRC) -o $@ $(LDFLAGS)

$(SDK_LIB):
	@echo "Missing SDK library: $(SDK_LIB)"
	@echo "Run: sh download-lib.sh"
	@exit 1

clean:
	rm -f $(TARGETS)
	rm -rf demo/*.dSYM

help:
	@echo "Build all C++ Revo3 examples: make -C c"
	@echo "Run auto detect:             ./c/demo/auto_detect"
	@echo "Run hand demo:               ./c/demo/hand_demo"
	@echo "Run DFU demo:                ./c/demo/hand_dfu firmware.bin"
	@echo "Run motor demo:              ./c/demo/revo3_motor"
	@echo "Manual Modbus:               ./c/demo/revo3_motor --modbus /dev/ttyUSB0 5000000 1"

.PHONY: all clean help
