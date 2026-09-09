# @runtime Jython
from ghidra.app.script import GhidraScript
print("jython-headless=" + str(isRunningHeadless()))
print("jython-args=" + ",".join(getScriptArgs()))
print("jython-program=" + currentProgram.getName())
runScript("NestedPlain.java", ["from-jython"])
printerr("jython-error-stream")
