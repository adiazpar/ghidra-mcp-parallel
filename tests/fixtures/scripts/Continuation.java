import ghidra.app.util.headless.HeadlessScript;
public class Continuation extends HeadlessScript {
    @Override public void run() throws Exception {
        println("mode="+(isImporting()?"import":"process"));
        if(getScriptArgs().length>1)setHeadlessImportDirectory(getScriptArgs()[1]);
        setHeadlessContinuationOption(HeadlessContinuationOption.valueOf(getScriptArgs()[0]));
    }
}
