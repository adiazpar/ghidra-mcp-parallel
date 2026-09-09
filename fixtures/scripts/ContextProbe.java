import ghidra.app.util.headless.HeadlessScript;

public class ContextProbe extends HeadlessScript {
    @Override public void run() throws Exception {
        println("headless=" + isRunningHeadless());
        println("importing=" + isImporting());
        println("program=" + currentProgram.getName());
        println("address=" + currentAddress);
        println("selection=" + currentSelection.getNumAddresses());
        println("args=" + String.join(",", getScriptArgs()));
        storeHeadlessValue("probe", "shared-with-nested");
        runScript("NestedProbe.java", new String[] {"nested-arg"});
        printerr("probe-error-stream");
        analyzeChanges(currentProgram);
        println("analysisTimeout=" + analysisTimeoutOccurred());
    }
}
