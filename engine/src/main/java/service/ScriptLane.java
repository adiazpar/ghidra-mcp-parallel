package service;

import static service.Json.*;
import com.google.gson.*;
import generic.jar.ResourceFile;
import java.io.*;
import java.lang.reflect.Field;
import java.util.*;
import ghidra.app.script.*;
import ghidra.app.util.headless.*;
import ghidra.program.model.address.*;
import ghidra.program.util.ProgramSelection;
import ghidra.app.plugin.core.analysis.AutoAnalysisManager;
import ghidra.util.task.TaskMonitorAdapter;

/** Version-pinned lifecycle adapter; all access occurs under the engine exclusive reservation. */
final class ScriptLane {
    final Engine engine;
    ScriptLane(Engine engine){this.engine=engine;}
    static class ScriptFailure extends Exception { final JsonObject output;ScriptFailure(Throwable cause,JsonObject output){super(cause);this.output=output;} }
    static class BoundedWriter extends Writer {
        final StringBuilder value=new StringBuilder();final int limit;boolean truncated;
        BoundedWriter(int limit){this.limit=limit;}
        public synchronized void write(char[] chars,int off,int len){int n=Math.min(len,limit-value.length());if(n>0)value.append(chars,off,n);if(n<len)truncated=true;}
        public void flush(){} public void close(){}
    }
    // Ghidra exposes script providers publicly, but the HeadlessScript lifecycle attachment
    // is package-private and its owning analyzer's project is private. Fail closed on API drift.
    static void set(HeadlessAnalyzer h,String field,Object value) throws Exception {
        Field f=HeadlessAnalyzer.class.getDeclaredField(field);f.setAccessible(true);f.set(h,value);
    }
    JsonObject run(Engine.Target t,JsonObject a,TaskMonitorAdapter monitor) throws Exception {
        BoundedWriter out=new BoundedWriter(engine.outputLimit/4),err=new BoundedWriter(engine.outputLimit/4);
        PrintWriter output=new PrintWriter(out,true),error=new PrintWriter(err,true);
        HeadlessAnalyzer h=HeadlessAnalyzer.getInstance();h.reset();set(h,"project",engine.project);
        h.getOptions().setRunScriptsNoImport(!bool(a,"importing",false),t.program.getName());
        h.getOptions().enableAnalysis(bool(a,"analyze",false));
        List<ResourceFile> paths=new ArrayList<>();
        if(arr(a,"paths").size()>16||arr(a,"properties_paths").size()>16)throw new IllegalArgumentException("Maximum 16 script/property directories");
        for(JsonElement path:arr(a,"paths")){
            ResourceFile rf=new ResourceFile(engine.local(path.getAsString()).toFile());
            if(!rf.isDirectory())throw new IllegalArgumentException("Script path is not a directory");paths.add(rf);
        }
        Address current=a.has("address")?engine.operations.address(t.program,a):t.program.getMinAddress();
        AddressSet set=new AddressSet();
        for(JsonElement range:arr(a,"selection")){JsonArray r=range.getAsJsonArray();set.add(t.program.getAddressFactory().getAddress(r.get(0).getAsString()),t.program.getAddressFactory().getAddress(r.get(1).getAsString()));}
        GhidraState state=new GhidraState(null,engine.project,t.program,new ghidra.program.util.ProgramLocation(t.program,current),new ProgramSelection(set),null);
        // Supply an existing provider interpreter so Jython executes synchronously on this lane.
        // This also captures Python print and lets exceptions propagate instead of being swallowed
        // by the provider's detached execution thread. Every job receives a fresh interpreter.
        var interpreter=ghidra.jython.GhidraJythonInterpreter.get();
        interpreter.setOut(output);interpreter.setErr(error);
        state.addEnvironmentVar("ghidra.jython.interpreter",interpreter);
        JsonArray executed=new JsonArray();String continuation="CONTINUE";
        JsonObject record=obj();
        java.net.URL[] urls=new java.net.URL[paths.size()];for(int i=0;i<paths.size();i++)urls[i]=paths.get(i).toURL();
        var compiledLoader=new java.net.URLClassLoader(urls,GhidraScript.class.getClassLoader());
        try {
            for(ResourceFile path:paths)GhidraScriptUtil.getBundleHost().add(path,true,false);
            JsonArray chain=new JsonArray();
            chain.addAll(arr(a,"pre_scripts"));chain.addAll(arr(a,"scripts"));
            if(a.has("name"))chain.add(obj("name",req(a,"name"),"args",arr(a,"args")));
            chain.add(obj("_analysis",true));chain.addAll(arr(a,"post_scripts"));
            if(chain.size()>32)throw new IllegalArgumentException("Maximum 32 scripts per job");
            for(JsonElement item:chain) {
                monitor.checkCancelled();JsonObject spec=item.getAsJsonObject();
                if(bool(spec,"_analysis",false)) {
                    Field enabled=HeadlessOptions.class.getDeclaredField("analyze");enabled.setAccessible(true);
                    if(enabled.getBoolean(h.getOptions())) {
                        TaskMonitorAdapter analysisMonitor=new TaskMonitorAdapter(true);
                        ghidra.util.task.CancelledListener listener=()->analysisMonitor.cancel();
                        monitor.addCancelledListener(listener);
                        var timer=java.util.concurrent.Executors.newSingleThreadScheduledExecutor();
                        var timeout=timer.schedule(()->analysisMonitor.cancel(),Math.max(1,num(a,"analysis_timeout",300)),java.util.concurrent.TimeUnit.SECONDS);
                        try {engine.analyze(t,a,analysisMonitor);}
                        catch(ghidra.util.exception.CancelledException ex){monitor.checkCancelled();set(h,"analysisTimedOut",true);record.addProperty("analysis_timed_out",true);}
                        finally{timeout.cancel(false);timer.shutdown();monitor.removeCancelledListener(listener);}
                    }
                    continue;
                }
                String scriptName=req(spec,"name");GhidraScript script;
                if(scriptName.endsWith(".class")) {
                    String className=scriptName.substring(0,scriptName.length()-6);
                    Class<? extends GhidraScript> cls=compiledLoader.loadClass(className).asSubclass(GhidraScript.class);
                    script=cls.getConstructor().newInstance();
                    File parent=new File(cls.getResource(cls.getSimpleName()+".class").toURI()).getParentFile();
                    script.setPropertiesFileLocation(parent.getAbsolutePath(),className);
                } else {
                    ResourceFile source=GhidraScriptUtil.findScriptByName(scriptName);
                    if(source==null)throw new FileNotFoundException(scriptName);
                    GhidraScriptProvider provider=GhidraScriptUtil.getProvider(source);
                    if(provider==null)throw new IllegalArgumentException("No provider for "+source);
                    script=provider.getScriptInstance(source,error);
                }
                if(script instanceof HeadlessScript hs) {
                    var attach=HeadlessScript.class.getDeclaredMethod("setHeadlessInstance",HeadlessAnalyzer.class);attach.setAccessible(true);attach.invoke(hs,h);
                    var initial=HeadlessScript.class.getDeclaredMethod("setInitialContinuationOption",HeadlessScript.HeadlessContinuationOption.class);initial.setAccessible(true);initial.invoke(hs,HeadlessScript.HeadlessContinuationOption.valueOf(continuation));
                }
                String[] args=new String[arr(spec,"args").size()];for(int i=0;i<args.length;i++)args[i]=arr(spec,"args").get(i).getAsString();
                script.setScriptArgs(args);
                List<ResourceFile> properties=new ArrayList<>();for(JsonElement p:arr(a,"properties_paths"))properties.add(new ResourceFile(engine.local(p.getAsString()).toFile()));
                script.setPotentialPropertiesFileLocations(properties);
                script.execute(state,new ScriptControls(output,error,false,monitor));
                executed.add(req(spec,"name"));
                if(script instanceof HeadlessScript hs){var get=HeadlessScript.class.getDeclaredMethod("getContinuationOption");get.setAccessible(true);continuation=get.invoke(hs).toString();}
                if(continuation.startsWith("ABORT"))break;
            }
            if(continuation.contains("DELETE")) {
                if(!bool(a,"importing",false)&&!bool(a,"allow_delete",false))throw new IllegalStateException("Deletion requested: allow_delete is required, equivalent to headless -okToDelete");
                record.addProperty("delete_requested",true);
            }
            Field folder=HeadlessAnalyzer.class.getDeclaredField("saveDomainFolder");folder.setAccessible(true);
            var saveFolder=(ghidra.framework.model.DomainFolder)folder.get(h);
            if(saveFolder!=null)record.addProperty("import_folder",saveFolder.getPathname());
            record.addProperty("continuation",continuation);
            return record;
        }catch(Throwable failure){throw new ScriptFailure(failure,record);}
        finally {
            try {
                Field enabled=HeadlessOptions.class.getDeclaredField("analyze");enabled.setAccessible(true);
                boolean drain=enabled.getBoolean(h.getOptions())&&!continuation.startsWith("ABORT");
                Set<ghidra.program.model.listing.Program> affected=new LinkedHashSet<>();affected.add(t.program);
                for(Engine.Target loaded:engine.targets.values())affected.add(loaded.program);
                for(var program:affected) {
                    program.flushEvents();AutoAnalysisManager manager=AutoAnalysisManager.getAnalysisManager(program);
                    int tx=program.startTransaction("Drain script analysis");
                    try { if(monitor.isCancelled()||!drain)manager.cancelQueuedTasks();else manager.waitForAnalysis(null,monitor); }
                    finally {program.endTransaction(tx,true);}
                }
            } finally {
                record.addProperty("stdout",out.value.toString());record.addProperty("stderr",err.value.toString());record.addProperty("truncated",out.truncated||err.truncated);record.add("executed",executed);
                try {interpreter.cleanup();compiledLoader.close();}
                finally {
                    state.removeEnvironmentVar("ghidra.jython.interpreter");
                    for(ResourceFile path:paths)GhidraScriptUtil.getBundleHost().remove(path);
                    h.reset();Thread.interrupted();
                }
            }
        }
    }
}
