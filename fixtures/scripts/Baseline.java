import ghidra.app.util.headless.HeadlessScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import java.util.Base64;
import java.nio.charset.StandardCharsets;

public class Baseline extends HeadlessScript {
    @Override public void run() throws Exception {
        DecompInterface d=new DecompInterface();
        DecompileOptions options=new DecompileOptions();options.grabFromProgram(currentProgram);options.setMaxPayloadMBytes(16);
        d.setOptions(options);d.openProgram(currentProgram);
        try {
            for(String name:getScriptArgs()) {
                var functions=currentProgram.getFunctionManager().getFunctions(true);
                for(var f:functions)if(f.getName().equals(name)) {
                    long start=System.nanoTime();var result=d.decompileFunction(f,60,monitor);
                    if(!result.decompileCompleted())throw new IllegalStateException(result.getErrorMessage());
                    println("BASELINE|"+name+"|"+((System.nanoTime()-start)/1e6)+"|"+Base64.getEncoder().encodeToString(result.getDecompiledFunction().getC().getBytes(StandardCharsets.UTF_8)));
                }
            }
            println("BINARY_SHA256|"+currentProgram.getExecutableSHA256());
        } finally { d.dispose(); }
    }
}
