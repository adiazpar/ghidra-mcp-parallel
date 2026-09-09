import ghidra.app.script.GhidraScript;
import ghidra.app.plugin.core.analysis.AutoAnalysisManager;
import ghidra.app.services.AbstractAnalyzer;
import ghidra.app.services.AnalyzerType;
import ghidra.program.model.listing.Program;
import ghidra.program.model.address.AddressSetView;
import ghidra.app.util.importer.MessageLog;
import ghidra.util.task.TaskMonitor;
import ghidra.util.exception.CancelledException;

public class SlowAnalyzer extends GhidraScript {
    @Override public void run() throws Exception {
        var analyzer=new AbstractAnalyzer("Fixture slow analyzer","Deterministic cancellation fixture",AnalyzerType.BYTE_ANALYZER) {
            @Override public boolean added(Program p,AddressSetView set,TaskMonitor monitor,MessageLog log) throws CancelledException {
                long end=System.nanoTime()+10000000000L;
                while(System.nanoTime()<end){monitor.checkCancelled();try{Thread.sleep(10);}catch(InterruptedException e){throw new CancelledException();}}
                return true;
            }
        };
        AutoAnalysisManager.getAnalysisManager(currentProgram).scheduleOneTimeAnalysis(analyzer,currentProgram.getMemory());
    }
}
