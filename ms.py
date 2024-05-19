import sheet
from ms_active_directory import *

print("starting ....")
domain = ADDomain("au.ucsc.edu")
print("domain connected")

session = domain.create_session_as_user("admin.chartier@au.ucsc.edu", "Power2theAdmin!")
print("session created")
desired_attrs = ["mail"]
single_group_member_list = session.find_members_of_group("au-slugworks-access", ["cn"])
print("group members found")

in_group = []
for user in single_group_member_list:

    # Access the attributes dictionary and get the value after 'cn'
    attributes = user.all_attributes
    cn_value = attributes["cn"]
    print(cn_value)
    in_group.append(cn_value)

sheet.get_sheet_data(False)
print("checking sheet data")
All = sheet.student_data.loc[
    sheet.student_data["3D Printing"].isin(["Access", "Override Access"])
]["CruzID"].values.tolist()
staff = sheet.staff_data["CruzID"].values.tolist()
print("sheet data checked")

All = All + staff
print("in_group", in_group)
print("all", All)

to_add = set(All) - set(in_group)
print("unadded", to_add)
to_remove = set(in_group) - set(All)
print("to_remove", to_remove)
print("math calculated")

print("adding students")
# for student in Unadded:
session.add_users_to_groups(list(to_add), ["au-slugworks-access"])

print("removing students")
# to_remove_nonstaff= set(to_remove) - set(staff)
# for student in to_remove:
session.remove_users_from_groups(list(to_remove), ["au-slugworks-access"])
