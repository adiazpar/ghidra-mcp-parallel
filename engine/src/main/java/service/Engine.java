package service;

import static service.Json.*;
import com.google.gson.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.locks.*;
import generic.jar.ResourceFile;
import ghidra.GhidraApplicationLayout;
import ghidra.GhidraLaunchable;
import ghidra.framework.*;
import ghidra.framework.model.*;
import ghidra.framework.project.DefaultProjectManager;
import ghidra.app.util.headless.*;
import ghidra.app.script.GhidraScriptUtil;
import ghidra.app.plugin.core.analysis.AutoAnalysisManager;
import ghidra.app.util.importer.*;
import ghidra.program.model.listing.Program;
import ghidra.util.task.TaskMonitorAdapter;
import ghidra.util.exception.CancelledException;

/** Sole project owner. The supervisor controls admission; the gate is defense in depth. */
public class Engine implements GhidraLaunchable {
    static final Set<String> READS = Set.of("query", "decompile", "decompile_batch", "programs", "capabilities");
    final String generation = UUID.randomUUID().toString();
    final Map<String,Target> targets = new LinkedHashMap<>();
    final ConcurrentMap<String,TaskMonitorAdapter> monitors = new ConcurrentHashMap<>();
    final ReentrantReadWriteLock gate = new ReentrantReadWriteLock(true);
    Path root;
    Project project;
    int maxPrograms, workers, outputLimit;
    Decompilers decompilers;
    Operations operations;
    ScriptLane scripts;
    BufferedWriter wire;
    ExecutorService readers, lane;
    volatile boolean stopping;

    static class Manager extends DefaultProjectManager {
        Manager() { super(); }
        @Override protected void updatePreferences() {}
    }
    static class Target {
        final Program program;
        final String id;
        final String generation = UUID.randomUUID().toString();
        long revision;
        Target(String id, Program p) { this.id=id; this.program=p; }
    }

    @Override public void launch(GhidraApplicationLayout layout, String[] args) throws Exception {
        root=Path.of(args[0]).toRealPath();
        int port=Integer.parseInt(args[1]);
        String secret=System.getenv("SERVICE_ENGINE_SECRET");
        Socket socket=new Socket(InetAddress.getLoopbackAddress(),port);
        socket.setTcpNoDelay(true);
        wire=new BufferedWriter(new OutputStreamWriter(socket.getOutputStream(),StandardCharsets.UTF_8));
        BufferedReader input=new BufferedReader(new InputStreamReader(socket.getInputStream(),StandardCharsets.UTF_8));
        send(obj("event","hello","secret",secret,"pid",ProcessHandle.current().pid()));
        JsonObject config=JsonParser.parseString(input.readLine()).getAsJsonObject();
        workers=num(config,"workers",2); maxPrograms=num(config,"max_programs",2); outputLimit=num(config,"output_bytes",1048576);
        HeadlessGhidraApplicationConfiguration app=new HeadlessGhidraApplicationConfiguration();
        app.setApplicationLogFile(root.resolve(".local/runtime/ghidra.log").toFile());
        app.setScriptLogFile(root.resolve(".local/runtime/scripts.log").toFile());
        Application.initializeApplication(layout,app);
        HeadlessAnalyzer.getInstance();
        GhidraScriptUtil.acquireBundleHostReference();
        GhidraScriptUtil.getProviders().add(0,new ServiceJythonScriptProvider());
        decompilers=new Decompilers(workers,num(config,"cache_entries",64),outputLimit);
        operations=new Operations(this);
        scripts=new ScriptLane(this);
        readers=Executors.newFixedThreadPool(workers);
        lane=Executors.newSingleThreadExecutor();
        send(obj("event","ready","generation",generation,"ghidra",Application.getApplicationVersion(),"workers",workers));
        try {
            String line;
            while((line=input.readLine())!=null) {
                if(line.length()>outputLimit) throw new IOException("IPC request too large");
                JsonObject request=JsonParser.parseString(line).getAsJsonObject();
                String op=req(request,"op"), id=str(request,"id","");
                if(op.equals("cancel")) { var m=monitors.get(id); if(m!=null)m.cancel(); continue; }
                if(op.equals("shutdown")) { stopping=true; break; }
                TaskMonitorAdapter monitor=new TaskMonitorAdapter(true);
                monitors.put(id,monitor);
                (READS.contains(op)?readers:lane).submit(()->execute(request,monitor));
            }
        } finally {
            monitors.values().forEach(TaskMonitorAdapter::cancel);
            readers.shutdown(); lane.shutdown();
            if(readers.awaitTermination(10,TimeUnit.SECONDS)&&lane.awaitTermination(10,TimeUnit.SECONDS)) {
                decompilers.close();
                for(Target t:targets.values()) t.program.release(this);
                targets.clear();
                if(project!=null)project.close();
                GhidraScriptUtil.releaseBundleHostReference();
            }
            socket.close();
            System.exit(0);
        }
    }
    synchronized void send(JsonObject value) throws IOException { wire.write(GSON.toJson(value));wire.newLine();wire.flush(); }
    void execute(JsonObject r,TaskMonitorAdapter m) {
        String id=req(r,"id"), op=req(r,"op");
        JsonObject a=sub(r,"args");
        boolean read=READS.contains(op);
        Lock lock=read?gate.readLock():gate.writeLock();
        lock.lock();
        long start=System.nanoTime();
        Target t=null;
        JsonObject result=obj("event","result","id",id,"generation",generation,"ghidra",Application.getApplicationVersion(),"status","completed","effect","none");
        try {
            send(obj("event","started","id",id,"backend_start_ns",start,"thread",Thread.currentThread().getName()));
            m.checkCancelled();
            if(a.has("program"))t=target(req(a,"program"));
            JsonElement value;
            switch(op) {
                case "capabilities": value=operations.capabilities();break;
                case "project_open": value=openProject(a);break;
                case "project_close":
                    if(!targets.isEmpty())throw new IllegalStateException("Close loaded programs first");
                    if(project!=null){project.close();project=null;} value=obj("closed",true);break;
                case "programs": value=programs();break;
                case "program_open": t=openProgram(req(a,"path"),m);value=identity(t);break;
                case "program_import":
                    result.addProperty("effect","partially_applied");
                    List<Target> existing=new ArrayList<>(targets.values());JsonObject imported;
                    try {imported=importProgram(a,m,result);}
                    finally {
                        if(a.has("pre_scripts")||a.has("post_scripts")){
                            for(Target affected:existing)affected.revision++;
                            decompilers.invalidate();
                        }
                    }
                    if(a.has("pre_scripts")||a.has("post_scripts"))for(Target affected:existing)save(affected,m);
                    value=imported;
                    if(imported.has("id"))t=target(req(imported,"id"));
                    result.addProperty("effect",bool(imported,"discarded",false)?"discarded":"applied");break;
                case "program_save": requireRevision(t,a);save(t,m);value=identity(t);break;
                case "program_close":
                    requireRevision(t,a);
                    if(bool(a,"save",true))save(t,m);
                    else if(t.program.isChanged()&&!bool(a,"discard",false))throw new IllegalArgumentException("Unsaved changes: save or explicitly discard");
                    decompilers.invalidate(); targets.remove(t.id); JsonObject closed=identity(t);t.program.release(this); t=null;value=closed;break;
                case "query": value=operations.query(t,a,m);break;
                case "decompile": value=decompilers.decompile(t,a,m);break;
                case "decompile_batch":
                    JsonArray batch=new JsonArray();
                    if(arr(a,"functions").size()>64)throw new IllegalArgumentException("Maximum batch size 64");
                    for(JsonElement f:arr(a,"functions")){m.checkCancelled();JsonObject opts=a.deepCopy();opts.add("function",f);opts.remove("functions");batch.add(decompilers.decompile(t,opts,m));}
                    value=batch;break;
                case "edit": requireRevision(t,a); value=operations.edit(t,a,m,result);break;
                case "analyze": case "script":
                    requireRevision(t,a);
                    result.addProperty("effect","partially_applied");
                    try { value=op.equals("script")?scripts.run(t,a,m):analyze(t,a,m); }
                    finally {
                        if(op.equals("script"))for(Target affected:targets.values())affected.revision++;
                        else t.revision++;
                        decompilers.invalidate();
                    }
                    result.addProperty("effect","applied");
                    if(op.equals("script")&&bool(value.getAsJsonObject(),"delete_requested",false)) {
                        var file=t.program.getDomainFile();targets.remove(t.id);t.program.release(this);t=null;file.delete();
                        result.addProperty("effect","deleted");
                    } else if(bool(a,"save",true)) {
                        if(op.equals("script"))for(Target affected:targets.values())save(affected,m);
                        else save(t,m);
                    }
                    break;
                case "export": requireRevision(t,a);value=operations.export(t,a,m);break;
                default: throw new IllegalArgumentException("Unknown operation: "+op);
            }
            result.add("output",value);
        } catch(Throwable e) {
            e.printStackTrace(System.err);
            result.addProperty("status",m.isCancelled()||e instanceof CancelledException?"cancelled":"failed");
            result.addProperty("error",e.toString());
            if(e instanceof ScriptLane.ScriptFailure sf)result.add("output",sf.output);
        } finally {
            if(t!=null&&!t.program.isClosed())result.add("program",identity(t));
            result.addProperty("backend_start_ns",start);
            result.addProperty("backend_end_ns",System.nanoTime());
            result.addProperty("compute_ms",(System.nanoTime()-start)/1e6);
            // Serialization occurs inside the reservation; nothing live escapes.
            if(GSON.toJson(result).getBytes(StandardCharsets.UTF_8).length>outputLimit) {
                result.remove("output");result.addProperty("status","failed");result.addProperty("error","Output exceeds configured bound; narrow query or batch");
            }
            try { send(result); }catch(IOException e){System.exit(3);}
            monitors.remove(id);lock.unlock();
        }
    }
    Target target(String id) { Target t=targets.get(id);if(t==null)throw new IllegalArgumentException("Program is not open: "+id);return t; }
    JsonObject identity(Target t) {
        return obj("id",t.id,"project",project.getName(),"generation",generation+"/"+t.generation,
            "revision",t.revision,"version",version(t),"durable",!t.program.isChanged(),
            "binary_sha256",t.program.getExecutableSHA256(),"name",t.program.getName(),
            "language",t.program.getLanguageID().toString());
    }
    String version(Target t) { return generation+"/"+t.generation+":"+t.revision; }
    void requireRevision(Target t,JsonObject a) { if(t==null)throw new IllegalArgumentException("program required");if(!version(t).equals(req(a,"expected_version")))throw new IllegalStateException("stale_revision; current="+version(t)); }
    Path local(String value) throws IOException {
        Path p=root.resolve(value).normalize().toAbsolutePath();
        if(!p.startsWith(root))throw new IllegalArgumentException("Path must be within checkout");
        Path ancestor=p;while(!Files.exists(ancestor))ancestor=ancestor.getParent();
        if(!ancestor.toRealPath().startsWith(root))throw new IllegalArgumentException("Path escapes checkout through link");
        return p;
    }
    JsonObject openProject(JsonObject a) throws Exception {
        if(project!=null)throw new IllegalStateException("Project already open");
        String name=req(a,"name");if(!name.matches("[A-Za-z0-9_-]{1,64}"))throw new IllegalArgumentException("Invalid project name");
        Path parent=local(str(a,"directory","runtime/projects"));Files.createDirectories(parent);
        ProjectLocator locator=new ProjectLocator(parent.toString(),name);
        Manager manager=new Manager();
        project=locator.exists()?manager.openProject(locator,false,false):manager.createProject(locator,null,false);
        return obj("project",name,"opened",true);
    }
    JsonObject programs() throws Exception {
        JsonArray loaded=new JsonArray(), files=new JsonArray();
        for(Target t:targets.values())loaded.add(identity(t));
        if(project!=null)listFolder(project.getProjectData().getRootFolder(),files);
        return obj("project",project==null?null:project.getName(),"loaded",loaded,"files",files);
    }
    void listFolder(DomainFolder folder,JsonArray files) throws Exception {
        for(DomainFile f:folder.getFiles()){if(files.size()>=10000)throw new IllegalStateException("Project listing limit");files.add(f.getPathname());}
        for(DomainFolder f:folder.getFolders())listFolder(f,files);
    }
    void capacity() { if(project==null)throw new IllegalStateException("Open project first");if(targets.size()>=maxPrograms)throw new IllegalStateException("Loaded program limit reached; close a target"); }
    Target openProgram(String path,TaskMonitorAdapter m) throws Exception {
        if(targets.containsKey(path))return targets.get(path);
        capacity();DomainFile f=project.getProjectData().getFile(path);
        if(f==null)throw new FileNotFoundException(path);
        Program p=(Program)f.getDomainObject(this,false,false,m);
        Target t=new Target(path,p);targets.put(path,t);AutoAnalysisManager.getAnalysisManager(p);return t;
    }
    JsonObject importProgram(JsonObject a,TaskMonitorAdapter m,JsonObject evidence) throws Exception {
        capacity();Path file=local(req(a,"file"));
        var builder=ProgramLoader.builder().source(file.toFile()).project(project).monitor(m);
        if(a.has("name"))builder.name(req(a,"name"));
        if(a.has("folder"))builder.projectFolderPath(req(a,"folder"));
        if(a.has("loader"))builder.loaders(req(a,"loader"));
        if(a.has("language"))builder.language(req(a,"language"));
        if(a.has("compiler"))builder.compiler(req(a,"compiler"));
        for(var e:sub(a,"loader_options").entrySet())builder.addLoaderArg(e.getKey(),e.getValue().getAsString());
        try(var loaded=builder.load()) {
            Program p=loaded.getPrimaryDomainObject(this);
            evidence.addProperty("binary_sha256",p.getExecutableSHA256());
            try {
                Target t=new Target("import",p);
                JsonObject lifecycle=new JsonObject();
                if(a.has("pre_scripts")||a.has("post_scripts")) {
                    JsonObject scriptArgs=a.deepCopy();scriptArgs.remove("name");scriptArgs.addProperty("importing",true);scriptArgs.addProperty("analyze",bool(a,"analyze",true));
                    lifecycle=scripts.run(t,scriptArgs,m);
                    if(bool(lifecycle,"delete_requested",false)){p.release(this);return obj("discarded",true,"script",lifecycle);}
                    if(lifecycle.has("import_folder"))loaded.getPrimary().setProjectFolderPath(req(lifecycle,"import_folder"));
                } else if(bool(a,"analyze",true))analyze(t,a,m);
                loaded.save(m);
                // Retain exactly this imported Program, rather than opening a second instance.
                String id=p.getDomainFile().getPathname();
                Target opened=new Target(id,p);targets.put(id,opened);JsonObject identity=identity(opened);identity.add("script",lifecycle);return identity;
            } catch(Exception e) {p.release(this);throw e;}
        }
    }
    JsonObject analyze(Target t,JsonObject a,TaskMonitorAdapter m) throws Exception {
        Program p=t.program;var manager=AutoAnalysisManager.getAnalysisManager(p);
        int tx=p.startTransaction("Service analysis");
        try { for(var e:sub(a,"analysis_options").entrySet()) {
            var options=p.getOptions(Program.ANALYSIS_PROPERTIES);String key=e.getKey();
            if(!options.contains(key))throw new IllegalArgumentException("Unknown analysis option "+key);
            Object old=options.getObject(key,null);JsonElement v=e.getValue();
            Object value;
            if(old instanceof java.io.File)value=local(v.getAsString()).toFile();
            else if(old instanceof Enum<?>)value=GSON.fromJson(v,old.getClass());
            else if(old==null||old instanceof String||old instanceof Number||old instanceof Boolean)value=old==null?v.getAsString():GSON.fromJson(v,old.getClass());
            else throw new IllegalArgumentException("Analysis option needs script-specific configuration: "+key);
            if(value==null)throw new IllegalArgumentException("Invalid analysis option value "+key);
            options.putObject(key,value);
        }
        manager.initializeOptions();
        if(bool(a,"all",true))manager.reAnalyzeAll(null);
        p.flushEvents();manager.startAnalysis(m);p.flushEvents();manager.waitForAnalysis(null,m);
        if(manager.isAnalyzing())throw new IllegalStateException("Analysis did not drain");
        m.checkCancelled();
        if(bool(a,"all",true))ghidra.program.util.GhidraProgramUtilities.markProgramAnalyzed(p);
        return obj("analysis_complete",true);
        } finally { p.endTransaction(tx,true); }
    }
    void save(Target t,TaskMonitorAdapter m) throws Exception { m.checkCancelled();t.program.save("Service save",m); }
}
