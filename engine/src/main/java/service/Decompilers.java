package service;

import static service.Json.*;
import com.google.gson.*;
import java.util.*;
import java.util.concurrent.*;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.util.task.TaskMonitor;

final class Decompilers implements AutoCloseable {
    static final class Worker { final int id; final DecompInterface api=new DecompInterface();Program program; Worker(int id){this.id=id;} }
    final BlockingQueue<Worker> pool;
    final List<Worker> all=new ArrayList<>();
    final Map<String,JsonObject> cache=new LinkedHashMap<>(16,.75f,true);
    final ConcurrentMap<String,CompletableFuture<JsonObject>> inFlight=new ConcurrentHashMap<>();
    final int cacheEntries,outputLimit;
    Decompilers(int count,int cacheEntries,int outputLimit) {
        this.cacheEntries=cacheEntries;this.outputLimit=outputLimit;pool=new ArrayBlockingQueue<>(count);
        for(int i=0;i<count;i++){Worker w=new Worker(i);all.add(w);pool.add(w);}
    }
    static Function function(Program p,String name) {
        var addr=p.getAddressFactory().getAddress(name);
        if(addr!=null){Function f=p.getFunctionManager().getFunctionContaining(addr);if(f!=null)return f;}
        Function found=null;
        for(Function f:p.getFunctionManager().getFunctions(true))if(f.getName().equals(name)||f.getName(true).equals(name)){
            if(found!=null)throw new IllegalArgumentException("Ambiguous function name; use address");found=f;
        }
        if(found==null)throw new IllegalArgumentException("Function not found: "+name);return found;
    }
    Worker lease(Program p,TaskMonitor m) throws Exception {
        Worker w;while((w=pool.poll(100,TimeUnit.MILLISECONDS))==null)m.checkCancelled();
        try {
            m.checkCancelled();
            if(w.program!=p){w.api.closeProgram();if(!w.api.openProgram(p))throw new IllegalStateException(w.api.getLastMessage());w.program=p;}
            // Reset all options on every lease. No client state leaks to the next job.
            DecompileOptions opts=new DecompileOptions();opts.grabFromProgram(p);opts.setMaxPayloadMBytes(16);
            w.api.setOptions(opts);w.api.toggleCCode(true);w.api.toggleSyntaxTree(true);w.api.setSimplificationStyle("decompile");
            return w;
        }catch(Exception e){release(w);throw e;}
    }
    void release(Worker w){pool.add(w);}
    JsonObject decompile(Engine.Target t,JsonObject args,TaskMonitor m) throws Exception {
        String name=req(args,"function");int timeout=Math.max(1,Math.min(300,num(args,"decompiler_timeout",60)));
        String key=t.generation+":"+t.revision+":"+GSON.toJson(args);
        if(bool(args,"cache",true))synchronized(cache){JsonObject hit=cache.get(key);if(hit!=null){hit=hit.deepCopy();hit.addProperty("cache_hit",true);return hit;}}
        CompletableFuture<JsonObject> own=new CompletableFuture<>();
        if(bool(args,"coalesce",true)) {
            CompletableFuture<JsonObject> other=inFlight.putIfAbsent(key,own);
            if(other!=null) {
                for(;;) {
                    m.checkCancelled();
                    try {JsonObject shared=other.get(100,TimeUnit.MILLISECONDS).deepCopy();shared.addProperty("coalesced",true);return shared;}
                    catch(TimeoutException ex){continue;}
                    catch(ExecutionException ex){break;} // cancelled/failed leader does not cancel another job
                }
                JsonObject retry=args.deepCopy();retry.addProperty("coalesce",false);return decompile(t,retry,m);
            }
        }
        try {
            JsonObject value=compute(t,args,m,timeout);
            if(bool(args,"cache",true))synchronized(cache){cache.put(key,value.deepCopy());while(cache.size()>cacheEntries)cache.remove(cache.keySet().iterator().next());}
            own.complete(value.deepCopy());return value;
        } catch(Exception e) {own.completeExceptionally(e);throw e;}
        finally {inFlight.remove(key,own);}
    }
    JsonObject compute(Engine.Target t,JsonObject args,TaskMonitor m,int timeout) throws Exception {
        String name=req(args,"function");
        Worker w=lease(t.program,m);
        try {
            Function f=function(t.program,name);long start=System.nanoTime();
            DecompileResults r=w.api.decompileFunction(f,timeout,m);long end=System.nanoTime();m.checkCancelled();
            if(!r.decompileCompleted())throw new IllegalStateException("Decompiler failed: "+r.getErrorMessage());
            String code=r.getDecompiledFunction().getC();if(code.length()>outputLimit/2)throw new IllegalStateException("Decompiled output bound exceeded");
            JsonArray vars=new JsonArray();var it=r.getHighFunction().getLocalSymbolMap().getSymbols();
            while(it.hasNext()){var s=it.next();vars.add(obj("name",s.getName(),"type",s.getDataType().getPathName()));}
            JsonObject value=obj("function",f.getName(),"address",f.getEntryPoint().toString(),"code",code,"variables",vars,
                "worker",w.id,"program_instance",System.identityHashCode(t.program),"native_start_ns",start,"native_end_ns",end,"cache_hit",false);
            return value;
        } finally {release(w);}
    }
    void invalidate(){synchronized(cache){cache.clear();}for(Worker w:all){w.api.closeProgram();w.program=null;}}
    @Override public void close(){for(Worker w:all)w.api.dispose();}
}
