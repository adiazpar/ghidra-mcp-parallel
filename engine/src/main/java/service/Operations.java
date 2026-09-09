package service;

import static service.Json.*;
import com.google.gson.*;
import java.util.*;
import java.nio.file.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.data.*;
import ghidra.program.model.pcode.*;
import ghidra.app.cmd.function.*;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.util.cparser.C.CParser;
import ghidra.app.util.parser.FunctionSignatureParser;
import ghidra.app.util.exporter.*;
import ghidra.app.script.GhidraScriptUtil;
import ghidra.util.classfinder.ClassSearcher;
import ghidra.util.task.TaskMonitorAdapter;

final class Operations {
    final Engine engine;
    Operations(Engine engine){this.engine=engine;}
    Address address(Program p,JsonObject a) {
        Address addr=p.getAddressFactory().getAddress(req(a,"address"));
        if(addr==null)throw new IllegalArgumentException("Invalid address");return addr;
    }
    JsonObject function(Function f){return obj("name",f.getName(true),"address",f.getEntryPoint().toString(),"signature",f.getPrototypeString(false,false),"size",f.getBody().getNumAddresses());}
    JsonObject capabilities() {
        JsonArray providers=new JsonArray(),exporters=new JsonArray();
        for(var p:GhidraScriptUtil.getProviders())providers.add(obj("name",p.getDescription(),"extension",p.getExtension(),"class",p.getClass().getName(),
            "available",!p.getClass().getName().contains("PyGhidra")&&!p.getClass().getName().contains("Stub")));
        for(var e:ClassSearcher.getInstances(Exporter.class))exporters.add(obj("name",e.getName(),"class",e.getClass().getName()));
        return obj("operations",List.of("project_open","project_close","program_open","program_import","program_close","program_save","programs","query","decompile","decompile_batch","edit","analyze","script","export"),
            "queries",List.of("functions","function","disassembly","xrefs_to","xrefs_from","function_xrefs","strings","data","symbols","namespaces","classes","imports","exports","segments","types","analysis_options","bytes"),
            "edits",List.of("rename_function","rename_data","rename_variable","comment","prototype","variable_type","define_type","apply_type","create_function","disassemble","namespace"),
            "script_providers",providers,"exporters",exporters,"script_reservation","engine_exclusive","atomic_edit_rollback",true);
    }
    JsonObject query(Engine.Target target,JsonObject a,TaskMonitorAdapter m) throws Exception {
        Program p=Objects.requireNonNull(target,"program required").program;
        String kind=req(a,"kind"), filter=str(a,"filter","").toLowerCase(Locale.ROOT);
        int offset=Math.max(0,num(a,"offset",0)),limit=Math.max(1,Math.min(1000,num(a,"limit",100)));
        List<JsonElement> records=new ArrayList<>();
        java.util.function.Consumer<JsonElement> add = v -> {
            if(filter.isEmpty()||GSON.toJson(v).toLowerCase(Locale.ROOT).contains(filter))records.add(v);
        };
        // Iteration stops at the requested page, bounding detached records independently of database size.
        int max=offset+limit+1;if(offset>1000000)throw new IllegalArgumentException("Offset limit exceeded");
        switch(kind) {
            case "function": add.accept(function(Decompilers.function(p,req(a,"function"))));break;
            case "functions":
                for(Function f:p.getFunctionManager().getFunctions(true)){m.checkCancelled();add.accept(function(f));if(records.size()>=max)break;}break;
            case "disassembly":
                Function f=Decompilers.function(p,req(a,"function"));
                for(Instruction i:p.getListing().getInstructions(f.getBody(),true)){m.checkCancelled();add.accept(obj("address",i.getAddress().toString(),"instruction",i.toString(),"comment",i.getComment(CommentType.EOL)));if(records.size()>=max)break;}break;
            case "xrefs_to":case "function_xrefs":case "xrefs_from":
                Address addr=kind.equals("function_xrefs")?Decompilers.function(p,req(a,"function")).getEntryPoint():address(p,a);
                Iterable<Reference> refs=kind.equals("xrefs_from")?Arrays.asList(p.getReferenceManager().getReferencesFrom(addr)):p.getReferenceManager().getReferencesTo(addr);
                for(Reference r:refs){m.checkCancelled();add.accept(obj("from",r.getFromAddress().toString(),"to",r.getToAddress().toString(),"type",r.getReferenceType().getName()));if(records.size()>=max)break;}break;
            case "strings":case "data":
                for(Data d:p.getListing().getDefinedData(true)){m.checkCancelled();if(kind.equals("strings")&&!d.hasStringValue())continue;
                    add.accept(obj("address",d.getAddress().toString(),"name",d.getLabel(),"type",d.getDataType().getPathName(),"value",String.valueOf(d.getValue())));if(records.size()>=max)break;}break;
            case "symbols":case "namespaces":case "classes":case "imports":case "exports":
                var symbols=p.getSymbolTable().getAllSymbols(true);
                while(symbols.hasNext()){m.checkCancelled();Symbol s=symbols.next();
                    if(kind.equals("namespaces")&&s.getSymbolType()!=SymbolType.NAMESPACE&&s.getSymbolType()!=SymbolType.CLASS)continue;
                    if(kind.equals("classes")&&s.getSymbolType()!=SymbolType.CLASS)continue;
                    if(kind.equals("imports")&&!s.isExternal())continue;
                    if(kind.equals("exports")&&!s.isExternalEntryPoint())continue;
                    add.accept(obj("name",s.getName(true),"address",s.getAddress().toString(),"type",s.getSymbolType().toString()));if(records.size()>=max)break;
                }break;
            case "segments":
                for(var b:p.getMemory().getBlocks())add.accept(obj("name",b.getName(),"start",b.getStart().toString(),"end",b.getEnd().toString(),"size",b.getSize(),"read",b.isRead(),"write",b.isWrite(),"execute",b.isExecute()));break;
            case "types":
                var types=p.getDataTypeManager().getAllDataTypes();while(types.hasNext()){m.checkCancelled();var d=types.next();add.accept(obj("name",d.getPathName(),"length",d.getLength(),"definition",d.toString()));if(records.size()>=max)break;}break;
            case "analysis_options":
                var options=p.getOptions(Program.ANALYSIS_PROPERTIES);for(String name:options.getOptionNames())add.accept(obj("name",name,"value",String.valueOf(options.getObject(name,null)),"type",options.getType(name).toString()));break;
            case "bytes":
                byte[] bytes=new byte[Math.min(65536,Math.max(1,num(a,"length",64)))];int read=p.getMemory().getBytes(address(p,a),bytes);add.accept(obj("hex",HexFormat.of().formatHex(Arrays.copyOf(bytes,read))));break;
            default:throw new IllegalArgumentException("Unknown query kind "+kind);
        }
        JsonArray items=new JsonArray();for(int i=offset;i<Math.min(records.size(),offset+limit);i++)items.add(records.get(i));
        return obj("items",items,"offset",offset,"has_more",records.size()>offset+limit);
    }
    DataType type(Program p,String text) throws Exception {
        DataType d=p.getDataTypeManager().getDataType(text.startsWith("/")?text:"/"+text);
        if(d!=null)return d;
        if(text.endsWith("*"))return new PointerDataType(type(p,text.substring(0,text.length()-1).trim()),p.getDataTypeManager());
        ArrayList<DataType> matches=new ArrayList<>();p.getDataTypeManager().findDataTypes(text,matches);
        if(matches.size()==1)return matches.getFirst();
        d=BuiltInDataTypeManager.getDataTypeManager().getDataType("/"+text);
        if(d==null)throw new IllegalArgumentException("Unknown or ambiguous datatype: "+text);return d;
    }
    JsonObject edit(Engine.Target target,JsonObject args,TaskMonitorAdapter m,JsonObject result) throws Exception {
        Program p=target.program;JsonArray changes=arr(args,"changes");
        if(changes.isEmpty()||changes.size()>100)throw new IllegalArgumentException("edit needs 1..100 changes");
        int tx=p.startTransaction("Service atomic edit");boolean commit=false;
        try {
            for(JsonElement e:changes){
                m.checkCancelled();apply(p,e.getAsJsonObject(),m);
                // Later changes in the same transaction may decompile renamed/retyped symbols.
                // They must not observe a native cache from an earlier change in this batch.
                engine.decompilers.invalidate();
            }
            m.checkCancelled();commit=true;
        }finally {
            p.endTransaction(tx,commit);
            // Pure edits do not implicitly auto-analyze; all queued mutation events are drained and discarded.
            p.flushEvents();ghidra.app.plugin.core.analysis.AutoAnalysisManager.getAnalysisManager(p).cancelQueuedTasks();
            engine.decompilers.invalidate();
            result.addProperty("effect",commit?"applied":"rolled_back");
            if(commit)target.revision++;
        }
        if(bool(args,"save",true))engine.save(target,m);
        return obj("changes_applied",changes.size());
    }
    void apply(Program p,JsonObject a,TaskMonitorAdapter m) throws Exception {
        String op=req(a,"op");
        switch(op) {
            case "rename_function": Decompilers.function(p,req(a,"function")).setName(req(a,"name"),SourceType.USER_DEFINED);break;
            case "rename_data": p.getSymbolTable().createLabel(address(p,a),req(a,"name"),SourceType.USER_DEFINED).setPrimary();break;
            case "comment": p.getListing().setComment(address(p,a),CommentType.valueOf(str(a,"type","EOL")),str(a,"text",""));break;
            case "prototype":
                Function f=Decompilers.function(p,req(a,"function"));
                var signature=new FunctionSignatureParser(p.getDataTypeManager(),null).parse(f.getSignature(),req(a,"signature").strip().replaceFirst(";\\s*$",""));
                var cmd=new ApplyFunctionSignatureCmd(f.getEntryPoint(),signature,SourceType.USER_DEFINED);
                if(!cmd.applyTo(p,m))throw new IllegalArgumentException(cmd.getStatusMsg());break;
            case "rename_variable":case "variable_type":
                var w=engine.decompilers.lease(p,m);
                try { var r=w.api.decompileFunction(Decompilers.function(p,req(a,"function")),60,m);
                    if(!r.decompileCompleted())throw new IllegalArgumentException(r.getErrorMessage());
                    var it=r.getHighFunction().getLocalSymbolMap().getSymbols();HighSymbol found=null;
                    while(it.hasNext()){var s=it.next();if(s.getName().equals(req(a,"variable"))){found=s;break;}}
                    if(found==null)throw new IllegalArgumentException("Variable not found");
                    HighFunctionDBUtil.updateDBVariable(found,op.equals("rename_variable")?req(a,"name"):found.getName(),op.equals("variable_type")?type(p,req(a,"type")):null,SourceType.USER_DEFINED);
                }finally{engine.decompilers.release(w);}break;
            case "define_type":
                var parser=new CParser(p.getDataTypeManager());
                DataType dt=parser.parse(req(a,"declaration"));
                if(dt==null)throw new IllegalArgumentException("Declaration did not define a type");
                p.getDataTypeManager().addDataType(dt,DataTypeConflictHandler.REPLACE_HANDLER);break;
            case "apply_type":
                Address addr=address(p,a);DataType d=type(p,req(a,"type"));
                if(bool(a,"clear",false))p.getListing().clearCodeUnits(addr,addr.add(d.getLength()-1),false);
                p.getListing().createData(addr,d);break;
            case "disassemble":
                Address start=address(p,a);AddressSet range=new AddressSet(start,start.add(Math.min(65536,Math.max(1,num(a,"length",256)))-1));
                var dis=new DisassembleCommand(start,range,true);if(!dis.applyTo(p,m))throw new IllegalArgumentException(dis.getStatusMsg());break;
            case "create_function":
                var create=new CreateFunctionCmd(req(a,"name"),address(p,a),null,SourceType.USER_DEFINED);
                if(!create.applyTo(p,m))throw new IllegalArgumentException(create.getStatusMsg());break;
            case "namespace": p.getSymbolTable().createNameSpace(p.getGlobalNamespace(),req(a,"name"),SourceType.USER_DEFINED);break;
            default: throw new IllegalArgumentException("Unknown edit operation "+op);
        }
    }
    JsonObject export(Engine.Target target,JsonObject a,TaskMonitorAdapter m) throws Exception {
        Path file=engine.local(req(a,"file"));if(Files.exists(file))throw new IllegalArgumentException("Export destination exists");Files.createDirectories(file.getParent());
        String format=str(a,"format","Ghidra Zip File");Exporter exporter=null;
        for(Exporter candidate:ClassSearcher.getInstances(Exporter.class))if(candidate.getName().equals(format)||candidate.getClass().getSimpleName().equals(format))exporter=candidate;
        if(exporter==null)throw new IllegalArgumentException("Unknown exporter; inspect capabilities");
        var options=exporter.getOptions(()->target.program);
        for(var requested:sub(a,"options").entrySet()) {
            var option=options.stream().filter(o->o.getName().equals(requested.getKey())).findFirst().orElseThrow(()->new IllegalArgumentException("Unknown exporter option "+requested.getKey()));
            if(!option.parseAndSetValueByType(requested.getValue().getAsString(),target.program.getAddressFactory()))throw new IllegalArgumentException("Invalid exporter option "+requested.getKey());
        }
        if(options!=null)exporter.setOptions(options);
        if(!exporter.export(file.toFile(),target.program,null,m))throw new IllegalStateException(exporter.getMessageLog().toString());
        return obj("file",engine.root.relativize(file).toString(),"size",Files.size(file),"format",exporter.getName());
    }
}
