.DEFAULT_GOAL := all

CXX ?= g++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -Wpedantic
ETHERCAT_PREFIX ?= /usr/local
CPPFLAGS += -I$(ETHERCAT_PREFIX)/include
LDFLAGS += -L$(ETHERCAT_PREFIX)/lib -Wl,-rpath,$(ETHERCAT_PREFIX)/lib
LDLIBS += -lethercat -pthread

COMMON_OBJECT := revo3_ethercat.o
MIT_PLAN_HEADER := ../../../common/revo3_mit_plan.hpp
TARGETS := revo3_pdo revo3_sdo revo3_benchmark

all: $(TARGETS)

revo3_pdo: revo3_pdo.o $(COMMON_OBJECT)
	$(CXX) $(LDFLAGS) $^ $(LDLIBS) -o $@

revo3_sdo: revo3_sdo.o $(COMMON_OBJECT)
	$(CXX) $(LDFLAGS) $^ $(LDLIBS) -o $@

revo3_benchmark: revo3_benchmark.o $(COMMON_OBJECT)
	$(CXX) $(LDFLAGS) $^ $(LDLIBS) -o $@

%.o: %.cpp revo3_ethercat.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

revo3_pdo.o: $(MIT_PLAN_HEADER)

grant-capabilities: revo3_pdo revo3_benchmark
	sudo setcap cap_ipc_lock,cap_sys_nice=eip revo3_pdo
	sudo setcap cap_ipc_lock,cap_sys_nice=eip revo3_benchmark

clean:
	rm -f $(TARGETS) *.o

.PHONY: all clean grant-capabilities
