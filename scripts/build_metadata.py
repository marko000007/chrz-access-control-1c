"""Generate stable catalog metadata; validate it using the actual 1C loader."""
import json
import uuid
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
MD = "http://v8.1c.ru/8.3/MDClasses"
V8 = "http://v8.1c.ru/8.1/data/core"
XR = "http://v8.1c.ru/8.3/xcf/readable"
CFG = "http://v8.1c.ru/8.1/data/enterprise/current-config"
for prefix,uri in [("",MD),("v8",V8),("xr",XR),("app","http://v8.1c.ru/8.2/managed-application/core"),("xsi","http://www.w3.org/2001/XMLSchema-instance")]:
    ET.register_namespace(prefix,uri)


def uid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL,"chrz-access-control/"+name))


def node(parent,name,text=None,namespace=MD):
    item=ET.SubElement(parent,"{"+namespace+"}"+name)
    if text is not None:item.text=str(text)
    return item


def title(properties,value):
    synonym=node(properties,"Synonym")
    for language in ["ru","en"]:
        item=node(synonym,"item",namespace=V8)
        node(item,"lang",language,V8);node(item,"content",value,V8)


def save(path,root):
    path.parent.mkdir(parents=True,exist_ok=True)
    ET.indent(root,space="\t")
    ET.ElementTree(root).write(path,encoding="utf-8",xml_declaration=True)


def catalog(spec, kind="Catalog"):
    name=spec["name"]
    root=ET.Element("{"+MD+"}MetaDataObject",{"version":"2.20","xmlns:cfg":CFG,"xmlns:xs":"http://www.w3.org/2001/XMLSchema"})
    item=node(root,kind);item.set("uuid",uid(kind+"/"+name))
    info=node(item,"InternalInfo")
    for category in ["Object","Ref","Selection","List","Manager"]:
        generated=node(info,"GeneratedType",namespace=XR);generated.set("name",kind+category+"."+name);generated.set("category",category)
        node(generated,"TypeId",uid(name+category+"TypeId"),XR);node(generated,"ValueId",uid(name+category+"ValueId"),XR)
    props=node(item,"Properties")
    node(props,"Name",name);title(props,spec["title"])
    standard = [("CodeLength",20),("DescriptionLength",150),("CodeType","String"),("CodeAllowedLength","Variable")] if kind=="Catalog" else [("NumberLength",11),("NumberType","String"),("NumberAllowedLength","Variable"),("NumberPeriodicity","Year"),("Posting","Deny")]
    for key,value in [*standard,("CheckUnique","true"),("Autonumbering","true"),("UseStandardCommands","true")]:node(props,key,value)
    children=node(item,"ChildObjects")
    for field,caption,field_type in spec["fields"]:
        attribute=node(children,"Attribute");attribute.set("uuid",uid(name+"/"+field))
        properties=node(attribute,"Properties");node(properties,"Name",field);title(properties,caption)
        value_type=node(properties,"Type");node(value_type,"Type",("cfg:"+field_type) if field_type.startswith(("CatalogRef.","DocumentRef.")) else "xs:"+field_type,V8)
        if field_type=="string":
            qualifiers=node(value_type,"StringQualifiers",namespace=V8);node(qualifiers,"Length",150,V8);node(qualifiers,"AllowedLength","Variable",V8)
    save(ROOT/"one_c/configuration"/(kind+"s")/(name+".xml"),root)


def main():
    schema=json.loads((ROOT/"one_c/schema.json").read_text())
    path=ROOT/"one_c/configuration/Configuration.xml"
    tree=ET.parse(path);configuration=tree.getroot().find("{"+MD+"}Configuration")
    props=configuration.find("{"+MD+"}Properties")
    props.find("{"+MD+"}Name").text="ChrzAccessControl"
    props.find("{"+MD+"}ScriptVariant").text="Russian"
    children=configuration.find("{"+MD+"}ChildObjects")
    for spec in schema["catalogs"]:
        if not any(child.tag=="{"+MD+"}Catalog" and child.text==spec["name"] for child in children):node(children,"Catalog",spec["name"])
        catalog(spec)
    for spec in schema.get("documents",[]):
        if not any(child.tag=="{"+MD+"}Document" and child.text==spec["name"] for child in children):node(children,"Document",spec["name"])
        catalog(spec,"Document")
    save(path,tree.getroot())


if __name__=="__main__":main()
