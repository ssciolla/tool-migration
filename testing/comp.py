import json

with open("wh_courses.json", "r") as wh_file:
    wh_courses = json.loads(wh_file.read())

wh_course_ids = [wh_course['id'] for wh_course in wh_courses]
wh_course_set = set(wh_course_ids)
print(f'Number of courses from warehouse: {len(wh_course_set)}')

with open("api_courses.json", "r") as api_file:
    api_courses = json.loads(api_file.read())

api_course_ids = [api_course['id'] for api_course in api_courses]
api_course_set = set(api_course_ids)
print(f'Number of courses from API: {len(api_course_set)}')

intersection = wh_course_set.intersection(api_course_set)
print(f'Number of courses in both lists: {len(intersection)}')

wh_diff = wh_course_set.difference(api_course_set)
print('Warehouse courses not in API courses:')
print(wh_diff)
wh_courses_not_in_api = []
for course_id in wh_diff:
    for wh_course in wh_courses:
        if course_id == wh_course["id"]:
            wh_courses_not_in_api.append(wh_course)
            break
print('First five courses:')
print(json.dumps(wh_courses_not_in_api[:5], indent=2))

print('API courses not in warehouse courses:')
api_diff = api_course_set.difference(wh_course_set)
print(api_diff)
api_courses_not_in_wh = []
for course_id in api_diff:
    for api_course in api_courses:
        if course_id == api_course["id"]:
            api_courses_not_in_wh.append(api_course)
            break
print('First five courses:')
print(json.dumps(api_courses_not_in_wh[:5], indent=2))
